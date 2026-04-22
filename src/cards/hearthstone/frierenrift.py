"""
FRIERENRIFT - Frieren-themed Hybrid Variant (MTG x Hearthstone)

Core hybrid rules:
1. Manual mana growth: no automatic +1 crystal each turn.
2. Attune action: once per turn, any card in hand can be exiled as a mana source.
3. Tri-color affinity: cards require persistent shard colors (Azure/Ember/Verdant)
   in addition to normal HS mana costs.

Card text prefixes:
  [AF:a/e/v]   -> Affinity requirement counts for Azure/Ember/Verdant.
"""

from __future__ import annotations

import re

from src.engine.game import make_minion, make_spell, make_hero, make_hero_power
from src.engine.types import (
    CardType,
    Color,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
)
from src.engine.queries import get_power, get_toughness
from src.cards.interceptor_helpers import (
    get_enemy_hero_id,
    get_enemy_minions,
    get_friendly_minions,
)


TRI_COLORS = ("azure", "ember", "verdant")


def _ensure_variant_resources(player) -> dict[str, int]:
    resources = getattr(player, "variant_resources", None)
    if not isinstance(resources, dict):
        resources = {}
    for key in TRI_COLORS:
        resources[key] = int(resources.get(key, 0) or 0)
    player.variant_resources = resources
    return resources


def _resources_for_player_id(state: GameState, player_id: str) -> dict[str, int]:
    if state is None:
        return {k: 0 for k in TRI_COLORS}
    player = state.players.get(player_id)
    if not player:
        return {k: 0 for k in TRI_COLORS}
    return _ensure_variant_resources(player)


def _has_affinity(state: GameState, player_id: str, req: dict[str, int]) -> bool:
    resources = _resources_for_player_id(state, player_id)
    for key, needed in req.items():
        if int(resources.get(key, 0)) < int(needed):
            return False
    return True


def _parse_numeric_cost(mana_cost: str | None) -> int:
    if not mana_cost:
        return 0
    nums = re.findall(r"\{(\d+)\}", mana_cost)
    return sum(int(n) for n in nums)


def _assign_affinity(
    card,
    *,
    azure: int = 0,
    ember: int = 0,
    verdant: int = 0,
    attune_colors: list[str] | tuple[str, ...] | None = None,
):
    req = {
        "azure": max(0, int(azure)),
        "ember": max(0, int(ember)),
        "verdant": max(0, int(verdant)),
    }
    req_nonzero = {k: v for k, v in req.items() if v > 0}
    base_cost = _parse_numeric_cost(card.mana_cost)

    if attune_colors is None:
        inferred = [k for k, v in req.items() if v > 0]
        attune_colors = inferred if inferred else ["azure"]
    normalized_attune = []
    for color in attune_colors:
        c = str(color).strip().lower()
        if c in TRI_COLORS and c not in normalized_attune:
            normalized_attune.append(c)
    if not normalized_attune:
        normalized_attune = ["azure"]

    color_map = {
        "azure": Color.BLUE,
        "ember": Color.RED,
        "verdant": Color.GREEN,
    }
    card.characteristics.colors = {color_map[c] for c in normalized_attune if c in color_map}

    def _dynamic_cost(obj: GameObject, state: GameState, _req=req_nonzero, _base=base_cost) -> int:
        if not _has_affinity(state, obj.controller, _req):
            return 99
        return _base

    setattr(card, "dynamic_cost", _dynamic_cost)
    setattr(card, "aether_affinity", req_nonzero)
    setattr(card, "aether_attune_colors", normalized_attune)

    tag = f"[AF:{req['azure']}/{req['ember']}/{req['verdant']}]"
    if not str(card.text).startswith("[AF:"):
        card.text = f"{tag} {card.text}".strip()
    return card


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


def _deal_enemy_hero(obj: GameObject, state: GameState, amount: int) -> list[Event]:
    hero = get_enemy_hero_id(obj, state)
    if not hero:
        return []
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": hero, "amount": amount, "source": obj.id},
            source=obj.id,
        )
    ]


# =============================================================================
# Heroes + Powers
# =============================================================================

FRIEREN_HERO = make_hero(
    name="Frieren, Last Great Mage",
    hero_class="Frieren",
    starting_life=30,
    text="Hero Power: Analyze Formula (Gain 1 Azure shard. If you have all 3 shard colors, draw a card.)",
)

MACHT_HERO = make_hero(
    name="Macht of El Dorado",
    hero_class="Macht",
    starting_life=30,
    text="Hero Power: Gold Hex (Gain 1 Ember shard. Deal 1 to the enemy hero.)",
)

FRIERENRIFT_HEROES = {
    "Frieren": FRIEREN_HERO,
    "Macht": MACHT_HERO,
}


def analyze_formula_effect(obj: GameObject, state: GameState) -> list[Event]:
    player = state.players.get(obj.controller)
    if not player:
        return []
    resources = _ensure_variant_resources(player)
    resources["azure"] = int(resources.get("azure", 0)) + 1
    events: list[Event] = []
    if all(int(resources.get(k, 0)) > 0 for k in TRI_COLORS):
        events.append(
            Event(
                type=EventType.DRAW,
                payload={"player": obj.controller, "count": 1},
                source=obj.id,
            )
        )
    return events


ANALYZE_FORMULA = make_hero_power(
    name="Analyze Formula",
    cost=2,
    text="Gain 1 Azure shard. If you have Azure, Ember, and Verdant, draw a card.",
    effect=analyze_formula_effect,
)


def gold_hex_effect(obj: GameObject, state: GameState) -> list[Event]:
    player = state.players.get(obj.controller)
    if not player:
        return []
    resources = _ensure_variant_resources(player)
    resources["ember"] = int(resources.get("ember", 0)) + 1
    return _deal_enemy_hero(obj, state, 1)


GOLD_HEX = make_hero_power(
    name="Gold Hex",
    cost=2,
    text="Gain 1 Ember shard. Deal 1 damage to the enemy hero.",
    effect=gold_hex_effect,
)


FRIERENRIFT_HERO_POWERS = {
    "Frieren": ANALYZE_FORMULA,
    "Macht": GOLD_HEX,
}


# =============================================================================
# Cards - Frieren Side
# =============================================================================

APPRENTICE_CASTER = _assign_affinity(
    make_minion(
        name="Apprentice Caster",
        attack=1,
        health=2,
        mana_cost="{1}",
        subtypes={"Human", "Mage"},
        text="A disciplined novice of continental magic.",
        rarity="common",
    ),
    azure=1,
    attune_colors=["azure"],
)


def fern_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if not target:
        return _deal_enemy_hero(obj, state, 1)
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": target, "amount": 1, "source": obj.id},
            source=obj.id,
        )
    ]


FERN_PRECISE_DISCIPLE = _assign_affinity(
    make_minion(
        name="Fern, Precise Disciple",
        attack=2,
        health=3,
        mana_cost="{2}",
        subtypes={"Human", "Mage"},
        text="Battlecry: Deal 1 damage to the highest-Attack enemy minion.",
        rarity="rare",
        battlecry=fern_battlecry,
    ),
    azure=1,
    attune_colors=["azure"],
)


STARK_VANGUARD_GUARDIAN = _assign_affinity(
    make_minion(
        name="Stark, Vanguard Guardian",
        attack=3,
        health=4,
        mana_cost="{3}",
        subtypes={"Human", "Warrior"},
        keywords={"taunt"},
        text="Taunt",
        rarity="rare",
    ),
    verdant=1,
    attune_colors=["verdant"],
)


def heiter_benediction_effect(obj: GameObject, _state: GameState, _targets=None) -> list[Event]:
    return [
        Event(
            type=EventType.ARMOR_GAIN,
            payload={"player": obj.controller, "amount": 3},
            source=obj.id,
        ),
        Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1},
            source=obj.id,
        ),
    ]


HEITER_BENEDICTION = _assign_affinity(
    make_spell(
        name="Heiter's Benediction",
        mana_cost="{2}",
        text="Gain 3 Armor. Draw a card.",
        spell_effect=heiter_benediction_effect,
        rarity="common",
    ),
    azure=1,
    attune_colors=["azure"],
)


def zoltraak_bolt_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if target:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={"target": target, "amount": 3, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        ]
    return _deal_enemy_hero(obj, state, 3)


ZOLTRAAK_BOLT = _assign_affinity(
    make_spell(
        name="Zoltraak Bolt",
        mana_cost="{2}",
        text="Deal 3 to the highest-Attack enemy minion. If none, deal 3 to the enemy hero.",
        spell_effect=zoltraak_bolt_effect,
        rarity="common",
    ),
    ember=1,
    attune_colors=["ember"],
)


def eisen_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Eisen, Wall of the Past — lockout + sustain.

    - While Eisen is on the battlefield, any damage targeted at your hero is
      redirected to gain you 1 armor instead (enemies can still attack your
      other minions; this is the "hero hunker" rule).
    - At the start of each turn (either player's), you gain 2 Armor.
    """

    def _damage_filter(event: Event, s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        target = event.payload.get("target")
        if not target:
            return False
        player = s.players.get(obj.controller)
        if not player or player.hero_id != target:
            return False
        return True

    def _damage_handler(_event: Event, _s: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.PREVENT,
            new_events=[
                Event(
                    type=EventType.ARMOR_GAIN,
                    payload={"player": obj.controller, "amount": 1},
                    source=obj.id,
                )
            ],
        )

    def _turnstart_filter(event: Event, _s: GameState) -> bool:
        return event.type == EventType.TURN_START

    def _turnstart_handler(_event: Event, _s: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.ARMOR_GAIN,
                    payload={"player": obj.controller, "amount": 2},
                    source=obj.id,
                )
            ],
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.PREVENT,
            filter=_damage_filter,
            handler=_damage_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_turnstart_filter,
            handler=_turnstart_handler,
            duration="while_on_battlefield",
        ),
    ]


EISEN_ANCIENT_SHIELD = _assign_affinity(
    make_minion(
        name="Eisen, Wall of the Past",
        attack=3,
        health=10,
        mana_cost="{6}",
        subtypes={"Dwarf", "Warrior"},
        keywords={"taunt"},
        text=(
            "Taunt. While Eisen is on the battlefield, damage to your hero is prevented "
            "and you gain 1 Armor instead. At the start of each turn, gain 2 Armor."
        ),
        rarity="legendary",
        setup_interceptors=eisen_setup,
    ),
    azure=1,
    verdant=1,
    attune_colors=["verdant"],
)


def flight_magic_circle_effect(obj: GameObject, _state: GameState, _targets=None) -> list[Event]:
    events = []
    for _ in range(2):
        events.append(
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    "controller": obj.controller,
                    "token": {
                        "name": "Mage Familiar",
                        "power": 2,
                        "toughness": 2,
                        "types": {CardType.MINION},
                        "subtypes": {"Spirit", "Mage"},
                    },
                },
                source=obj.id,
            )
        )
    return events


FLIGHT_MAGIC_CIRCLE = _assign_affinity(
    make_spell(
        name="Flight Magic Circle",
        mana_cost="{4}",
        text="Summon two 2/2 Mage Familiars.",
        spell_effect=flight_magic_circle_effect,
        rarity="rare",
    ),
    azure=1,
    verdant=1,
    attune_colors=["azure", "verdant"],
)


def grimoire_archive_effect(obj: GameObject, _state: GameState, _targets=None) -> list[Event]:
    return [
        Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 2}, source=obj.id)
    ]


GRIMOIRE_ARCHIVE = _assign_affinity(
    make_spell(
        name="Grimoire Archive",
        mana_cost="{3}",
        text="Draw 2 cards.",
        spell_effect=grimoire_archive_effect,
        rarity="common",
    ),
    azure=2,
    attune_colors=["azure"],
)


def fern_follow_up_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": oid, "amount": 1, "source": obj.id, "from_spell": True},
            source=obj.id,
        )
        for oid in _enemy_minion_ids(obj, state)
    ]


FERN_FOLLOW_UP = _assign_affinity(
    make_spell(
        name="Fern's Follow-Up",
        mana_cost="{1}",
        text="Deal 1 damage to all enemy minions.",
        spell_effect=fern_follow_up_effect,
        rarity="common",
    ),
    azure=1,
    attune_colors=["azure"],
)


def frieren_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Frieren, Mage of the Age — mana engine + regenerate.

    1. Death memory: whenever any minion dies, stamp the current turn on Frieren.
    2. End of controller's turn: if no minion has died this turn, gain 1 max mana.
    3. Damage to Frieren is fully prevented; her damage_marked is cleared
       (regenerate — elves slow-time past the wound).
    """

    def _death_filter(event: Event, _s: GameState) -> bool:
        return event.type == EventType.OBJECT_DESTROYED

    def _death_handler(_event: Event, s: GameState) -> InterceptorResult:
        # Stamp turn number where a death last occurred.
        setattr(obj, "_frieren_last_death_turn", int(getattr(s, "turn_number", 0) or 0))
        return InterceptorResult(action=InterceptorAction.PASS)

    def _endturn_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.PHASE_END:
            return False
        if event.payload.get("phase") != "end":
            return False
        return event.payload.get("player") == obj.controller

    def _endturn_handler(_event: Event, s: GameState) -> InterceptorResult:
        turn_no = int(getattr(s, "turn_number", 0) or 0)
        last_death = int(getattr(obj, "_frieren_last_death_turn", -1) or -1)
        if last_death == turn_no:
            return InterceptorResult(action=InterceptorAction.PASS)
        player = s.players.get(obj.controller)
        if not player:
            return InterceptorResult(action=InterceptorAction.PASS)
        # Slow-time reward: a mana crystal blooms this turn and stays.
        if getattr(player, "mana_crystals", 0) < 10:
            player.mana_crystals = int(getattr(player, "mana_crystals", 0)) + 1
        return InterceptorResult(action=InterceptorAction.PASS)

    def _damage_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        return event.payload.get("target") == obj.id

    def _damage_handler(_event: Event, _s: GameState) -> InterceptorResult:
        # Regenerate: clear any accumulated damage and prevent the new hit.
        obj.state.damage = 0
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_death_filter,
            handler=_death_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_endturn_filter,
            handler=_endturn_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.PREVENT,
            filter=_damage_filter,
            handler=_damage_handler,
            duration="while_on_battlefield",
        ),
    ]


FRIEREN_LAST_GREAT_MAGE = _assign_affinity(
    make_minion(
        name="Frieren, Mage of the Age",
        attack=5,
        health=7,
        mana_cost="{7}",
        subtypes={"Elf", "Mage"},
        text=(
            "Regenerate (prevent all damage dealt to Frieren; she clears marked damage). "
            "At end of your turn, if no minion died this turn, gain a mana crystal "
            "(long-memory elves slow time past the wound)."
        ),
        rarity="legendary",
        setup_interceptors=frieren_setup,
    ),
    azure=2,
    verdant=1,
    attune_colors=["azure", "verdant"],
)


def journey_to_aureole_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events = _deal_enemy_hero(obj, state, 4)
    for oid in _enemy_minion_ids(obj, state):
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 4, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )
    return events


JOURNEY_TO_AUREOLE = _assign_affinity(
    make_spell(
        name="Journey to Aureole",
        mana_cost="{7}",
        text="Deal 4 damage to all enemies.",
        spell_effect=journey_to_aureole_effect,
        rarity="epic",
    ),
    azure=1,
    ember=1,
    verdant=1,
    attune_colors=["azure", "ember", "verdant"],
)


def aura_severing_ray_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if not target:
        return []
    return [
        Event(type=EventType.SILENCE_TARGET, payload={"target": target}, source=obj.id),
        Event(
            type=EventType.DAMAGE,
            payload={"target": target, "amount": 2, "source": obj.id, "from_spell": True},
            source=obj.id,
        ),
    ]


AURA_SEVERING_RAY = _assign_affinity(
    make_spell(
        name="Aura Severing Ray",
        mana_cost="{2}",
        text="Silence the highest-Attack enemy minion, then deal 2 damage to it.",
        spell_effect=aura_severing_ray_effect,
        rarity="rare",
    ),
    azure=1,
    ember=1,
    attune_colors=["azure", "ember"],
)


def canon_of_souls_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events: list[Event] = []
    for oid in _enemy_minion_ids(obj, state):
        events.append(Event(type=EventType.FREEZE_TARGET, payload={"target": oid}, source=obj.id))
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 1, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )
    return events


CANON_OF_SOULS = _assign_affinity(
    make_spell(
        name="Canon of Souls",
        mana_cost="{5}",
        text="Freeze all enemy minions. Deal 1 damage to them.",
        spell_effect=canon_of_souls_effect,
        rarity="rare",
    ),
    azure=1,
    ember=1,
    attune_colors=["azure", "ember"],
)


def himmel_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Himmel, Legacy of the Brave — delayed alt-win condition.

    - While Himmel is on the battlefield, at the start of each of your turns,
      if no minion of yours has attacked since Himmel entered play, deal
      4 damage to the enemy hero (legacy unbroken).
    - When one of yours attacks, the streak is severed.
    - On arrival, stamp the current turn so we count from *after* ETB.
    """

    def _attack_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get("attacker")
        if not attacker_id:
            return False
        return event.payload.get("controller") == obj.controller or (
            attacker_id in getattr(_s, "objects", {})
            and _s.objects[attacker_id].controller == obj.controller
        )

    def _attack_handler(_event: Event, _s: GameState) -> InterceptorResult:
        setattr(obj, "_himmel_streak_broken", True)
        return InterceptorResult(action=InterceptorAction.PASS)

    def _etb_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (
            event.payload.get("object_id") == obj.id
            and event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
        )

    def _etb_handler(_event: Event, s: GameState) -> InterceptorResult:
        setattr(obj, "_himmel_streak_broken", False)
        setattr(obj, "_himmel_etb_turn", int(getattr(s, "turn_number", 0) or 0))
        return InterceptorResult(action=InterceptorAction.PASS)

    def _turnstart_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.TURN_START:
            return False
        return event.payload.get("player") == obj.controller

    def _turnstart_handler(_event: Event, s: GameState) -> InterceptorResult:
        # Only fire on turns *after* Himmel entered.
        etb_turn = int(getattr(obj, "_himmel_etb_turn", -1) or -1)
        cur = int(getattr(s, "turn_number", 0) or 0)
        if cur <= etb_turn:
            return InterceptorResult(action=InterceptorAction.PASS)
        if getattr(obj, "_himmel_streak_broken", False):
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=_deal_enemy_hero(obj, s, 4),
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
            filter=_attack_filter,
            handler=_attack_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_turnstart_filter,
            handler=_turnstart_handler,
            duration="while_on_battlefield",
        ),
    ]


HIMMELS_LEGACY = _assign_affinity(
    make_minion(
        name="Himmel, Legacy of the Brave",
        attack=5,
        health=5,
        mana_cost="{6}",
        subtypes={"Human", "Hero"},
        text=(
            "Battlecry: Gain 4 Armor. At the start of each of your turns, if no minion "
            "of yours has attacked since Himmel entered, deal 4 damage to the enemy hero."
        ),
        rarity="legendary",
        battlecry=lambda obj, _s: [
            Event(
                type=EventType.ARMOR_GAIN,
                payload={"player": obj.controller, "amount": 4},
                source=obj.id,
            )
        ],
        setup_interceptors=himmel_setup,
    ),
    azure=1,
    verdant=1,
    attune_colors=["verdant"],
)


# =============================================================================
# Cards - Macht Side
# =============================================================================

SUPPLICANT_ADEPT = _assign_affinity(
    make_minion(
        name="Supplicant Adept",
        attack=1,
        health=3,
        mana_cost="{1}",
        subtypes={"Demon", "Mage"},
        text="Deathrattle: Gain 1 Armor.",
        rarity="common",
        deathrattle=lambda obj, _s: [
            Event(
                type=EventType.ARMOR_GAIN,
                payload={"player": obj.controller, "amount": 1},
                source=obj.id,
            )
        ],
    ),
    ember=1,
    attune_colors=["ember"],
)


LINIE_PERFECT_COPY = _assign_affinity(
    make_minion(
        name="Linie, Perfect Copy",
        attack=3,
        health=2,
        mana_cost="{2}",
        subtypes={"Demon"},
        text="Battlecry: Deal 1 damage to the enemy hero.",
        rarity="rare",
        battlecry=lambda obj, s: _deal_enemy_hero(obj, s, 1),
    ),
    ember=1,
    attune_colors=["ember"],
)


def draht_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if not target:
        return []
    return [Event(type=EventType.FREEZE_TARGET, payload={"target": target}, source=obj.id)]


DRAHT_BINDING_THREAD = _assign_affinity(
    make_minion(
        name="Draht, Binding Thread",
        attack=3,
        health=4,
        mana_cost="{3}",
        subtypes={"Demon", "Mage"},
        text="Battlecry: Freeze the highest-Attack enemy minion.",
        rarity="rare",
        battlecry=draht_battlecry,
    ),
    ember=1,
    verdant=1,
    attune_colors=["ember", "verdant"],
)


MACHT_GOLD_GUARD = _assign_affinity(
    make_minion(
        name="Macht's Gold Guard",
        attack=4,
        health=5,
        mana_cost="{4}",
        subtypes={"Demon", "Construct"},
        keywords={"taunt"},
        text="Taunt",
        rarity="common",
    ),
    ember=1,
    verdant=1,
    attune_colors=["verdant"],
)


def gold_curse_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events = _deal_enemy_hero(obj, state, 2)
    events.append(
        Event(
            type=EventType.ARMOR_GAIN,
            payload={"player": obj.controller, "amount": 2},
            source=obj.id,
        )
    )
    return events


GOLD_CURSE = _assign_affinity(
    make_spell(
        name="Gold Curse",
        mana_cost="{2}",
        text="Deal 2 damage to the enemy hero. Gain 2 Armor.",
        spell_effect=gold_curse_effect,
        rarity="common",
    ),
    ember=1,
    attune_colors=["ember"],
)


def blood_sigil_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events = [
        Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 1}, source=obj.id)
    ]
    player = state.players.get(obj.controller)
    if player and player.hero_id:
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": player.hero_id, "amount": 1, "source": obj.id},
                source=obj.id,
            )
        )
    return events


BLOOD_SIGIL = _assign_affinity(
    make_spell(
        name="Blood Sigil",
        mana_cost="{1}",
        text="Draw a card. Deal 1 damage to your hero.",
        spell_effect=blood_sigil_effect,
        rarity="common",
    ),
    ember=1,
    attune_colors=["ember"],
)


def demon_suppression_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": oid, "amount": 2, "source": obj.id, "from_spell": True},
            source=obj.id,
        )
        for oid in _enemy_minion_ids(obj, state)
    ]


DEMON_SUPPRESSION = _assign_affinity(
    make_spell(
        name="Demon Suppression",
        mana_cost="{3}",
        text="Deal 2 damage to all enemy minions.",
        spell_effect=demon_suppression_effect,
        rarity="rare",
    ),
    ember=1,
    verdant=1,
    attune_colors=["ember", "verdant"],
)


def solitar_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Solitar, Shadowchord — selection/deck-ID break.

    Tracks the last spell name any opponent has cast. Battlecry is encoded here
    via an ETB interceptor (rather than the ``battlecry`` hook) so we share the
    same state with the passive tracker.

    On ETB: copy the enemy's last-cast spell (if remembered) into your hand as
    a free attunement — its cost becomes 0 while on the stack, so it plays like
    an extra card drawn from the opponent's deck.
    """

    def _opp_spell_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = (
            event.payload.get("caster")
            or event.payload.get("controller")
            or event.controller
        )
        # Remember opponent spells; fall back to source object controller check.
        if caster and caster == obj.controller:
            return False
        if caster and caster in s.players and caster != obj.controller:
            return True
        source_obj = s.objects.get(event.source)
        return source_obj is not None and source_obj.controller != obj.controller

    def _opp_spell_handler(event: Event, s: GameState) -> InterceptorResult:
        # Try to grab the card definition by walking the spell source object.
        spell_obj = s.objects.get(
            event.payload.get("spell_id")
            or event.payload.get("card_id")
            or event.source
        )
        if spell_obj and getattr(spell_obj, "card_def", None) is not None:
            setattr(obj, "_solitar_memorized", spell_obj.card_def)
        return InterceptorResult(action=InterceptorAction.PASS)

    def _etb_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (
            event.payload.get("object_id") == obj.id
            and event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
            and event.payload.get("from_zone_type") == ZoneType.HAND
        )

    def _etb_handler(_event: Event, _s: GameState) -> InterceptorResult:
        memorized = getattr(obj, "_solitar_memorized", None)
        if memorized is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.ADD_TO_HAND,
                    payload={
                        "player": obj.controller,
                        "card_def": memorized,
                        "cost_override": 0,
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
            filter=_opp_spell_filter,
            handler=_opp_spell_handler,
            duration="while_on_battlefield",
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=_etb_filter,
            handler=_etb_handler,
            duration="while_on_battlefield",
        ),
    ]


SOLITAR_MIRAGE = _assign_affinity(
    make_minion(
        name="Solitar, Shadowchord",
        attack=5,
        health=5,
        mana_cost="{6}",
        subtypes={"Demon"},
        keywords={"stealth"},
        text=(
            "Stealth. While Solitar is on the battlefield, remember the last spell any "
            "opponent cast. Battlecry: Add a copy of that spell to your hand; it costs 0."
        ),
        rarity="legendary",
        setup_interceptors=solitar_setup,
    ),
    ember=1,
    azure=1,
    attune_colors=["azure", "ember"],
)


def aura_execution_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    Aura's Scales of Obedience: destroy every enemy minion with Attack strictly
    less than Aura's Attack; freeze the rest. Asymmetric sweeper keyed to the
    Attack axis — power-down effects from your hand punish enemy boards twice.
    """
    aura_attack = int(get_power(obj, state) or 0)
    events: list[Event] = []
    for oid in _enemy_minion_ids(obj, state):
        enemy = state.objects.get(oid)
        if not enemy:
            continue
        enemy_attack = int(get_power(enemy, state) or 0)
        if enemy_attack < aura_attack:
            events.append(
                Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": oid, "reason": "scales_of_obedience"},
                    source=obj.id,
                )
            )
        else:
            events.append(
                Event(
                    type=EventType.FREEZE_TARGET,
                    payload={"target": oid},
                    source=obj.id,
                )
            )
    return events


AURA_EXECUTION_SAINT = _assign_affinity(
    make_minion(
        name="Aura, Execution Saint",
        attack=6,
        health=6,
        mana_cost="{7}",
        subtypes={"Demon"},
        text=(
            "Battlecry: Destroy every enemy minion with Attack less than Aura's Attack. "
            "Freeze the rest. Scales of Obedience."
        ),
        rarity="legendary",
        battlecry=aura_execution_battlecry,
    ),
    ember=2,
    verdant=1,
    attune_colors=["ember"],
)


def el_dorado_collapse_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events = _deal_enemy_hero(obj, state, 4)
    for oid in _enemy_minion_ids(obj, state):
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 4, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )
    return events


EL_DORADO_COLLAPSE = _assign_affinity(
    make_spell(
        name="El Dorado Collapse",
        mana_cost="{7}",
        text="Deal 4 damage to all enemies.",
        spell_effect=el_dorado_collapse_effect,
        rarity="epic",
    ),
    azure=1,
    ember=1,
    verdant=1,
    attune_colors=["azure", "ember", "verdant"],
)


QUAL_VENOM_LANCE = _assign_affinity(
    make_spell(
        name="Qual's Venom Lance",
        mana_cost="{2}",
        text="Deal 3 damage to the highest-Attack enemy minion.",
        spell_effect=zoltraak_bolt_effect,
        rarity="common",
    ),
    ember=1,
    attune_colors=["ember"],
)


def imperial_standard_deathrattle(obj: GameObject, _state: GameState) -> list[Event]:
    return [
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                "controller": obj.controller,
                "token": {
                    "name": "Imperial Soldier",
                    "power": 2,
                    "toughness": 2,
                    "types": {CardType.MINION},
                    "subtypes": {"Soldier"},
                },
            },
            source=obj.id,
        )
    ]


IMPERIAL_STANDARD = _assign_affinity(
    make_minion(
        name="Imperial Standard",
        attack=2,
        health=6,
        mana_cost="{4}",
        subtypes={"Demon", "Banner"},
        keywords={"taunt"},
        text="Taunt. Deathrattle: Summon a 2/2 Imperial Soldier.",
        rarity="rare",
        deathrattle=imperial_standard_deathrattle,
    ),
    verdant=1,
    ember=1,
    attune_colors=["verdant"],
)


def severing_guillotine_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if not target:
        return []
    return [
        Event(
            type=EventType.OBJECT_DESTROYED,
            payload={"object_id": target, "reason": "severing_guillotine"},
            source=obj.id,
        )
    ]


SEVERING_GUILLOTINE = _assign_affinity(
    make_spell(
        name="Severing Guillotine",
        mana_cost="{5}",
        text="Destroy the highest-Attack enemy minion.",
        spell_effect=severing_guillotine_effect,
        rarity="rare",
    ),
    ember=2,
    attune_colors=["ember"],
)


FEARSOME_BATTALION = _assign_affinity(
    make_minion(
        name="Fearsome Battalion",
        attack=4,
        health=3,
        mana_cost="{3}",
        subtypes={"Demon", "Soldier"},
        text="Relentless formation pressure.",
        rarity="common",
    ),
    ember=1,
    verdant=1,
    attune_colors=["ember"],
)


def golden_rain_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    events = _deal_enemy_hero(obj, state, 1)
    for oid in _enemy_minion_ids(obj, state):
        events.append(
            Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": 1, "source": obj.id, "from_spell": True},
                source=obj.id,
            )
        )
    events.append(Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 1}, source=obj.id))
    return events


GOLDEN_RAIN = _assign_affinity(
    make_spell(
        name="Golden Rain",
        mana_cost="{3}",
        text="Deal 1 damage to all enemies. Draw a card.",
        spell_effect=golden_rain_effect,
        rarity="common",
    ),
    ember=1,
    azure=1,
    attune_colors=["ember", "azure"],
)


def macht_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Macht, Golden General — resource-axis break on the Attune action itself.

    While Macht is on the battlefield, his controller may Attune a second time
    each turn (attunements_per_turn = 2). After every spell their side casts,
    the opponent loses 1 mana crystal (if any) — the gold hex taxes the enemy's
    own ramp, mirroring Frieren's shard growth.

    Stored fields (cleaned up on departure via leaves-battlefield interceptor):
      player._macht_active  — sentinel so we don't stack attune bonuses
    """

    # Grant the Attune bonus the moment Macht arrives.
    def _grant_attune_bonus(state: GameState) -> None:
        player = state.players.get(obj.controller)
        if not player or getattr(player, "_macht_active", False):
            return
        setattr(
            player,
            "_macht_prior_attune_cap",
            int(getattr(player, "attunements_per_turn", 1) or 1),
        )
        player.attunements_per_turn = int(getattr(player, "attunements_per_turn", 1) or 1) + 1
        setattr(player, "_macht_active", True)

    def _etb_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        return (
            event.payload.get("object_id") == obj.id
            and event.payload.get("to_zone_type") == ZoneType.BATTLEFIELD
        )

    def _etb_handler(_event: Event, s: GameState) -> InterceptorResult:
        _grant_attune_bonus(s)
        return InterceptorResult(action=InterceptorAction.PASS)

    def _leaves_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("object_id") != obj.id:
            return False
        return event.payload.get("from_zone_type") == ZoneType.BATTLEFIELD

    def _leaves_handler(_event: Event, s: GameState) -> InterceptorResult:
        player = s.players.get(obj.controller)
        if player and getattr(player, "_macht_active", False):
            cap = int(getattr(player, "_macht_prior_attune_cap", 1) or 1)
            player.attunements_per_turn = cap
            setattr(player, "_macht_active", False)
        return InterceptorResult(action=InterceptorAction.PASS)

    def _spell_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        caster = (
            event.payload.get("caster")
            or event.payload.get("controller")
            or event.controller
        )
        if caster and caster == obj.controller:
            return True
        source_obj = s.objects.get(event.source)
        return source_obj is not None and source_obj.controller == obj.controller

    def _spell_handler(_event: Event, s: GameState) -> InterceptorResult:
        events: list[Event] = []
        enemy_hero = get_enemy_hero_id(obj, s)
        if enemy_hero:
            events.append(
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": enemy_hero, "amount": 1, "source": obj.id},
                    source=obj.id,
                )
            )
        # Gold hex tax: opponent loses one available mana crystal (if possible).
        for pid, player in s.players.items():
            if pid == obj.controller:
                continue
            if getattr(player, "mana_crystals_available", 0) > 0:
                player.mana_crystals_available = int(player.mana_crystals_available) - 1
            break
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=events,
        )

    # Immediate apply (covers cases where ETB event already fired before setup runs).
    _grant_attune_bonus(_state)

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
            filter=_leaves_filter,
            handler=_leaves_handler,
            duration="permanent",
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


MACHT_GOLDEN_GENERAL = _assign_affinity(
    make_minion(
        name="Macht, Golden General",
        attack=7,
        health=8,
        mana_cost="{8}",
        subtypes={"Demon", "Lord"},
        text=(
            "While Macht is on the battlefield, you may Attune an additional time each turn. "
            "After you cast a spell, deal 1 damage to the enemy hero and the opponent loses "
            "one available mana crystal."
        ),
        rarity="legendary",
        setup_interceptors=macht_setup,
    ),
    ember=2,
    verdant=1,
    attune_colors=["ember"],
)


# =============================================================================
# New Legendaries — signature moments that lean on mode mechanics
# =============================================================================


def heiter_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    Heiter's benediction scales with attune history: the number of shards he
    has witnessed (sum of all three resources) becomes a cost reduction and a
    draw. Reward for committed tri-color decks.
    """
    resources = _resources_for_player_id(state, obj.controller)
    shard_total = sum(int(resources.get(k, 0)) for k in TRI_COLORS)
    events: list[Event] = [
        Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "count": 1},
            source=obj.id,
        )
    ]
    # Heal your hero for shard_total (generosity of the Goddess).
    player = state.players.get(obj.controller)
    if player and player.hero_id and shard_total > 0:
        events.append(
            Event(
                type=EventType.LIFE_CHANGE,
                payload={
                    "target": player.hero_id,
                    "amount": shard_total,
                    "source": obj.id,
                },
                source=obj.id,
            )
        )
    return events


def heiter_deathrattle(obj: GameObject, state: GameState) -> list[Event]:
    """
    Death rattle: resurrect a friendly minion from your graveyard with the
    smallest mana cost (Heiter mourns the youngest fallen).
    """
    gy_key = f"graveyard_{obj.controller}"
    gy = state.zones.get(gy_key)
    if not gy:
        return []

    candidates: list[tuple[int, str]] = []
    for oid in gy.objects:
        if oid == obj.id:
            continue
        other = state.objects.get(oid)
        if not other or CardType.MINION not in other.characteristics.types:
            continue
        cost = _parse_numeric_cost(
            getattr(other, "mana_cost", None)
            or getattr(other.characteristics, "mana_cost", "")
        )
        candidates.append((cost, oid))

    if not candidates:
        return []
    candidates.sort(key=lambda pair: pair[0])
    target_id = candidates[0][1]
    return [
        Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                "object_id": target_id,
                "player": obj.controller,
                "destination": "battlefield",
                "source": "heiter_deathrattle",
            },
            source=obj.id,
        )
    ]


HEITER_PRIEST_OF_THE_GODDESS = _assign_affinity(
    make_minion(
        name="Heiter, Priest of the Goddess",
        attack=3,
        health=5,
        mana_cost="{5}",
        subtypes={"Human", "Priest"},
        text=(
            "Battlecry: Draw a card and heal your hero for the total number of shards "
            "you have accumulated. Deathrattle: Resurrect the lowest-cost friendly minion "
            "from your graveyard."
        ),
        rarity="legendary",
        battlecry=heiter_battlecry,
        deathrattle=heiter_deathrattle,
    ),
    azure=2,
    attune_colors=["azure"],
)


def stark_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    Stark, Breakthrough — tutor break.
    Search your deck, reveal up to three minions with subtype Warrior, and
    put them into your hand as attune-0 cards (cost stays the same mana-wise;
    the attune-0 tag lives on the hand-side ``card_def.attune_cost`` override).
    """
    library_key = f"library_{obj.controller}"
    library = state.zones.get(library_key)
    if not library:
        return []

    picked: list[str] = []
    events: list[Event] = []
    for oid in list(library.objects):
        card = state.objects.get(oid)
        if not card:
            continue
        if "Warrior" not in card.characteristics.subtypes:
            continue
        picked.append(oid)
        if len(picked) >= 3:
            break

    for oid in picked:
        card = state.objects.get(oid)
        if not card:
            continue
        events.append(
            Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": oid,
                    "from_zone": library_key,
                    "from_zone_type": ZoneType.LIBRARY,
                    "to_zone": f"hand_{obj.controller}",
                    "to_zone_type": ZoneType.HAND,
                },
                source=obj.id,
            )
        )
    return events


def stark_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """Each time Stark attacks, he gains +1/+1 until end of turn (scaling)."""

    def _attack_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        return event.payload.get("attacker") == obj.id

    def _attack_handler(_event: Event, _s: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        "object_id": obj.id,
                        "power_mod": 1,
                        "toughness_mod": 1,
                        "duration": "end_of_turn",
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
            filter=_attack_filter,
            handler=_attack_handler,
            duration="while_on_battlefield",
        )
    ]


STARK_BREAKTHROUGH = _assign_affinity(
    make_minion(
        name="Stark, Breakthrough",
        attack=4,
        health=6,
        mana_cost="{5}",
        subtypes={"Human", "Warrior"},
        text=(
            "Battlecry: Search your deck for up to three Warrior minions; put them "
            "into your hand. Whenever Stark attacks, gain +1/+1 this turn."
        ),
        rarity="legendary",
        battlecry=stark_battlecry,
        setup_interceptors=stark_setup,
    ),
    verdant=2,
    attune_colors=["verdant"],
)


def sein_setup(obj: GameObject, _state: GameState) -> list[Interceptor]:
    """
    Sein, Cleric Companion — rewards heavy attune play.
    At the end of each turn, the controller's hero heals for
    (attunements performed this turn) x 2.
    """

    def _endturn_filter(event: Event, _s: GameState) -> bool:
        if event.type != EventType.PHASE_END:
            return False
        if event.payload.get("phase") != "end":
            return False
        return event.payload.get("player") == obj.controller

    def _endturn_handler(_event: Event, s: GameState) -> InterceptorResult:
        player = s.players.get(obj.controller)
        if not player:
            return InterceptorResult(action=InterceptorAction.PASS)
        attunes = int(getattr(player, "attunements_this_turn", 0) or 0)
        if attunes <= 0 or not player.hero_id:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={
                        "target": player.hero_id,
                        "amount": attunes * 2,
                        "source": obj.id,
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
            filter=_endturn_filter,
            handler=_endturn_handler,
            duration="while_on_battlefield",
        )
    ]


SEIN_CLERIC_COMPANION = _assign_affinity(
    make_minion(
        name="Sein, Cleric Companion",
        attack=2,
        health=5,
        mana_cost="{4}",
        subtypes={"Human", "Cleric"},
        text=(
            "At end of your turn, your hero heals for twice the number of times you "
            "Attuned this turn."
        ),
        rarity="legendary",
        setup_interceptors=sein_setup,
    ),
    azure=1,
    verdant=1,
    attune_colors=["azure", "verdant"],
)


def aurelia_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    """
    The Demon Lord Aurelia — reality-bender.

    Zero out each opponent's mana crystals_available *and* mana_crystals (they
    begin growing again next turn, at one per turn), and grant the controller
    10 mana crystals (to the cap). Each opponent also discards one shard of
    each color they have (affinity-axis break).
    """
    events: list[Event] = []
    for pid, player in state.players.items():
        if pid == obj.controller:
            continue
        player.mana_crystals_available = 0
        player.mana_crystals = 0
        resources = _ensure_variant_resources(player)
        for key in TRI_COLORS:
            if resources[key] > 0:
                resources[key] -= 1
        player.variant_resources = resources

    player = state.players.get(obj.controller)
    if player:
        player.mana_crystals = 10
        player.mana_crystals_available = 10
    # Silence every enemy minion (mythic presence).
    for oid in _enemy_minion_ids(obj, state):
        events.append(
            Event(
                type=EventType.SILENCE_TARGET,
                payload={"target": oid},
                source=obj.id,
            )
        )
    return events


def aurelia_dynamic_cost(obj, state: GameState) -> int:
    """
    Aurelia costs 1 less for each non-Human minion (Elf/Dwarf/Demon) the
    controller controls. Min cost 5. This bypasses the normal affinity gate
    because legendary-class cost reduction is the set's 'demon lord' hallmark.

    Accepts either a GameObject (engine path) or a CardDefinition (test path);
    in either case, we read ``mana_cost`` and prefer the object's controller
    over any ``last_controller`` stamp on the card def.
    """
    controller_id = getattr(obj, "controller", None) or getattr(obj, "last_controller", None)
    if not controller_id and state:
        controller_id = getattr(state, "active_player", None)
    # mana_cost lives on the card def / characteristics for GameObjects; direct
    # on CardDefinition objects. Fall back gracefully.
    raw_cost = (
        getattr(obj, "mana_cost", None)
        or getattr(getattr(obj, "card_def", None), "mana_cost", None)
        or getattr(getattr(obj, "characteristics", None), "mana_cost", None)
        or ""
    )
    base = _parse_numeric_cost(raw_cost)
    if not state or not controller_id:
        return base
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return base
    reduction = 0
    for oid in battlefield.objects:
        m = state.objects.get(oid)
        if not m or m.controller != controller_id:
            continue
        if CardType.MINION not in m.characteristics.types:
            continue
        subs = m.characteristics.subtypes or set()
        if subs & {"Elf", "Dwarf", "Demon"}:
            reduction += 1
    return max(5, base - reduction)


AURELIA_DEMON_LORD = _assign_affinity(
    make_minion(
        name="The Demon Lord Aurelia",
        attack=8,
        health=8,
        mana_cost="{9}",
        subtypes={"Demon", "Lord"},
        text=(
            "Costs 1 less for each Elf, Dwarf, or Demon you control (min 5). "
            "Battlecry: Your mana crystals become 10. Each opponent's mana crystals "
            "become 0 and they lose one shard of each color. Silence every enemy minion."
        ),
        rarity="legendary",
        battlecry=aurelia_battlecry,
    ),
    ember=3,
    attune_colors=["ember"],
)
# Override the affinity-gated dynamic cost with the mythic cost-reduction rule
# while still enforcing affinity at cast-time (we wrap _assign_affinity's gate).
_aurelia_affinity_gate = AURELIA_DEMON_LORD.dynamic_cost


def _aurelia_cost(card, state: GameState) -> int:
    gated = _aurelia_affinity_gate(card, state)
    if gated >= 99:
        return gated
    return aurelia_dynamic_cost(card, state)


AURELIA_DEMON_LORD.dynamic_cost = _aurelia_cost


def eternal_flame_effect(obj: GameObject, state: GameState, _targets=None) -> list[Event]:
    """
    Eternal Flame of Ethos — mythic sweeper + persistent shard hall-pass.

    1. Destroy every minion (both sides).
    2. Grant each player 1 of every shard color (one burst of colorless truth).
    3. Both players gain 1 max mana crystal (the flame tempers the world).
    """
    events: list[Event] = []
    for pid, player in state.players.items():
        if getattr(player, "mana_crystals", 0) < 10:
            player.mana_crystals = int(getattr(player, "mana_crystals", 0)) + 1
        resources = _ensure_variant_resources(player)
        for key in TRI_COLORS:
            resources[key] = int(resources.get(key, 0)) + 1
        player.variant_resources = resources

    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in list(battlefield.objects):
            mob = state.objects.get(oid)
            if not mob or CardType.MINION not in mob.characteristics.types:
                continue
            events.append(
                Event(
                    type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": oid, "reason": "eternal_flame"},
                    source=obj.id,
                )
            )
    return events


ETERNAL_FLAME_OF_ETHOS = _assign_affinity(
    make_spell(
        name="Eternal Flame of Ethos",
        mana_cost="{8}",
        text=(
            "Destroy all minions. Each player gains 1 shard of each color and "
            "1 max mana crystal."
        ),
        spell_effect=eternal_flame_effect,
        rarity="legendary",
    ),
    azure=1,
    ember=1,
    verdant=1,
    attune_colors=["azure", "ember", "verdant"],
)


# =============================================================================
# Decks
# =============================================================================

FRIERENRIFT_FRIEREN_DECK = [
    APPRENTICE_CASTER,
    APPRENTICE_CASTER,
    FERN_PRECISE_DISCIPLE,
    FERN_PRECISE_DISCIPLE,
    STARK_VANGUARD_GUARDIAN,
    STARK_VANGUARD_GUARDIAN,
    HEITER_BENEDICTION,
    HEITER_BENEDICTION,
    ZOLTRAAK_BOLT,
    ZOLTRAAK_BOLT,
    EISEN_ANCIENT_SHIELD,  # Eisen, Wall of the Past (legendary, unique)
    FLIGHT_MAGIC_CIRCLE,
    FLIGHT_MAGIC_CIRCLE,
    GRIMOIRE_ARCHIVE,
    GRIMOIRE_ARCHIVE,
    FERN_FOLLOW_UP,
    FERN_FOLLOW_UP,
    AURA_SEVERING_RAY,
    AURA_SEVERING_RAY,
    CANON_OF_SOULS,
    CANON_OF_SOULS,
    HIMMELS_LEGACY,  # legendary, unique
    JOURNEY_TO_AUREOLE,
    JOURNEY_TO_AUREOLE,
    FRIEREN_LAST_GREAT_MAGE,  # legendary, unique
    HEITER_PRIEST_OF_THE_GODDESS,  # new legendary
    STARK_BREAKTHROUGH,  # new legendary
    SEIN_CLERIC_COMPANION,  # new legendary
    ETERNAL_FLAME_OF_ETHOS,  # mythic sweeper
    APPRENTICE_CASTER,
]

FRIERENRIFT_MACHT_DECK = [
    SUPPLICANT_ADEPT,
    SUPPLICANT_ADEPT,
    LINIE_PERFECT_COPY,
    LINIE_PERFECT_COPY,
    DRAHT_BINDING_THREAD,
    DRAHT_BINDING_THREAD,
    MACHT_GOLD_GUARD,
    MACHT_GOLD_GUARD,
    GOLD_CURSE,
    GOLD_CURSE,
    BLOOD_SIGIL,
    BLOOD_SIGIL,
    DEMON_SUPPRESSION,
    DEMON_SUPPRESSION,
    SOLITAR_MIRAGE,  # Solitar, Shadowchord — legendary, unique
    AURA_EXECUTION_SAINT,  # legendary, unique
    EL_DORADO_COLLAPSE,
    EL_DORADO_COLLAPSE,
    QUAL_VENOM_LANCE,
    QUAL_VENOM_LANCE,
    IMPERIAL_STANDARD,
    IMPERIAL_STANDARD,
    SEVERING_GUILLOTINE,
    SEVERING_GUILLOTINE,
    FEARSOME_BATTALION,
    FEARSOME_BATTALION,
    GOLDEN_RAIN,
    GOLDEN_RAIN,
    MACHT_GOLDEN_GENERAL,  # legendary, unique
    AURELIA_DEMON_LORD,  # mythic legendary
]

FRIERENRIFT_DECKS = {
    "Frieren": FRIERENRIFT_FRIEREN_DECK,
    "Macht": FRIERENRIFT_MACHT_DECK,
}

assert len(FRIERENRIFT_FRIEREN_DECK) == 30
assert len(FRIERENRIFT_MACHT_DECK) == 30


# =============================================================================
# Global Modifiers
# =============================================================================

def install_frierenrift_modifiers(game) -> None:
    """
    Install global rules for Frierenrift hybrid mode.

    - Enable manual mana growth + one attune per turn for each player.
    - Triad Resonance: At start of your turn, if you have at least one Azure,
      Ember, and Verdant shard, draw 1 card.
    """
    state = game.state
    player_ids = list(state.players.keys())
    if not player_ids:
        return

    for pid in player_ids:
        player = state.players[pid]
        player.manual_mana_growth = True
        player.attunements_per_turn = 1
        player.attunements_this_turn = 0
        _ensure_variant_resources(player)

    def _turn_start_filter(event: Event, _s: GameState) -> bool:
        return event.type == EventType.TURN_START

    def _turn_start_handler(event: Event, s: GameState) -> InterceptorResult:
        active_pid = event.payload.get("player")
        if not active_pid or active_pid not in s.players:
            return InterceptorResult(action=InterceptorAction.PASS)

        resources = _resources_for_player_id(s, active_pid)
        if all(int(resources.get(k, 0)) > 0 for k in TRI_COLORS):
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[
                    Event(
                        type=EventType.DRAW,
                        payload={"player": active_pid, "count": 1},
                        source="frierenrift_triad_resonance",
                    )
                ],
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(
        Interceptor(
            id=f"mod_frierenrift_turnstart_{new_id()}",
            source="global_modifier",
            controller=player_ids[0],
            priority=InterceptorPriority.REACT,
            filter=_turn_start_filter,
            handler=_turn_start_handler,
            duration="permanent",
        )
    )


FRIERENRIFT_CARD_POOL = sorted(
    {card.name: card for deck in FRIERENRIFT_DECKS.values() for card in deck}.values(),
    key=lambda c: c.name,
)


__all__ = [
    "FRIERENRIFT_HEROES",
    "FRIERENRIFT_HERO_POWERS",
    "FRIERENRIFT_DECKS",
    "FRIERENRIFT_CARD_POOL",
    "install_frierenrift_modifiers",
]
