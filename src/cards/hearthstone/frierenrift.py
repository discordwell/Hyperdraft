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
    new_id,
)
from src.engine.queries import get_power, get_toughness
from src.cards.interceptor_helpers import get_enemy_hero_id, get_enemy_minions


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


def eisen_deathrattle(obj: GameObject, _state: GameState) -> list[Event]:
    return [
        Event(
            type=EventType.ARMOR_GAIN,
            payload={"player": obj.controller, "amount": 2},
            source=obj.id,
        )
    ]


EISEN_ANCIENT_SHIELD = _assign_affinity(
    make_minion(
        name="Eisen, Ancient Shield",
        attack=3,
        health=6,
        mana_cost="{4}",
        subtypes={"Dwarf", "Warrior"},
        keywords={"taunt"},
        text="Taunt. Deathrattle: Gain 2 Armor.",
        rarity="epic",
        deathrattle=eisen_deathrattle,
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
    def _spell_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source_obj = s.objects.get(event.source)
        return source_obj is not None and source_obj.controller == obj.controller

    def _spell_handler(_event: Event, _s: GameState) -> InterceptorResult:
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
            filter=_spell_filter,
            handler=_spell_handler,
            duration="while_on_battlefield",
        )
    ]


FRIEREN_LAST_GREAT_MAGE = _assign_affinity(
    make_minion(
        name="Frieren, Last Great Mage",
        attack=5,
        health=7,
        mana_cost="{6}",
        subtypes={"Elf", "Mage"},
        text="After you cast a spell, draw a card.",
        rarity="legendary",
        setup_interceptors=frieren_setup,
    ),
    azure=2,
    verdant=1,
    attune_colors=["azure"],
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


HIMMELS_LEGACY = _assign_affinity(
    make_minion(
        name="Himmel's Legacy",
        attack=5,
        health=5,
        mana_cost="{5}",
        subtypes={"Human", "Hero"},
        text="Battlecry: Gain 4 Armor.",
        rarity="epic",
        battlecry=lambda obj, _s: [
            Event(
                type=EventType.ARMOR_GAIN,
                payload={"player": obj.controller, "amount": 4},
                source=obj.id,
            )
        ],
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


SOLITAR_MIRAGE = _assign_affinity(
    make_minion(
        name="Solitar's Mirage",
        attack=5,
        health=5,
        mana_cost="{5}",
        subtypes={"Demon"},
        keywords={"stealth"},
        text="Stealth",
        rarity="epic",
    ),
    ember=1,
    azure=1,
    attune_colors=["azure", "ember"],
)


def aura_execution_battlecry(obj: GameObject, state: GameState) -> list[Event]:
    target = _highest_attack_enemy_minion_id(obj, state)
    if not target:
        return []
    return [
        Event(
            type=EventType.DAMAGE,
            payload={"target": target, "amount": 4, "source": obj.id},
            source=obj.id,
        )
    ]


AURA_EXECUTION_SAINT = _assign_affinity(
    make_minion(
        name="Aura, Execution Saint",
        attack=6,
        health=6,
        mana_cost="{6}",
        subtypes={"Demon"},
        text="Battlecry: Deal 4 damage to the highest-Attack enemy minion.",
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
    def _spell_filter(event: Event, s: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        source_obj = s.objects.get(event.source)
        return source_obj is not None and source_obj.controller == obj.controller

    def _spell_handler(_event: Event, s: GameState) -> InterceptorResult:
        enemy_hero = get_enemy_hero_id(obj, s)
        if not enemy_hero:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DAMAGE,
                    payload={"target": enemy_hero, "amount": 2, "source": obj.id},
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


MACHT_GOLDEN_GENERAL = _assign_affinity(
    make_minion(
        name="Macht, Golden General",
        attack=7,
        health=8,
        mana_cost="{7}",
        subtypes={"Demon", "Lord"},
        text="After you cast a spell, deal 2 damage to the enemy hero.",
        rarity="legendary",
        setup_interceptors=macht_setup,
    ),
    ember=2,
    verdant=1,
    attune_colors=["ember"],
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
    EISEN_ANCIENT_SHIELD,
    EISEN_ANCIENT_SHIELD,
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
    HIMMELS_LEGACY,
    HIMMELS_LEGACY,
    JOURNEY_TO_AUREOLE,
    JOURNEY_TO_AUREOLE,
    FRIEREN_LAST_GREAT_MAGE,
    APPRENTICE_CASTER,
    GRIMOIRE_ARCHIVE,
    ZOLTRAAK_BOLT,
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
    SOLITAR_MIRAGE,
    SOLITAR_MIRAGE,
    AURA_EXECUTION_SAINT,
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
    MACHT_GOLDEN_GENERAL,
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

