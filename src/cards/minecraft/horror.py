"""Box of Horrors — horror-themed Minecraft TCG expansion.

Inspiration:
  - Canon scary mobs: Phantom, Wither family, Sculk, Vex, Shulker, Endermite,
    Drowned, Husk, Stray, Silverfish, Magma Cube.
  - Modern horror mods: From The Fog (Man From The Fog), Cave Dweller (Gargin),
    Mimicer / Mimic Dweller, Skinwalker, Goatman, Backrooms.
  - Classic creepypasta: Null, Entity 303, the urban-legend Stalker.

Mechanical themes:
  - "Horror" subtype — broad lord/anchor for the set; a few cards key off it.
  - "Stalker" subtype — chasing-from-the-shadows sub-faction; bias toward
    Climb / Haste / on-attack chip damage.
  - "Spirit" subtype — incorporeal sub-faction; bias toward Aerial.
  - Mind erosion — a handful of effects discard cards from the opponent's hand
    (newest first; deterministic so AI doesn't need a choice prompt).
  - Wither rot — on_attack hooks that permanently shrink the mobs they hit.
  - Night Hunter — leverages the existing day/night phase for +1/+1 swings.

The set re-uses the make_mob / make_structure / make_tool / make_action
factories from alpha; no new engine surface is required.
"""

from __future__ import annotations

from src.engine.types import (
    CardDefinition,
    Characteristics,
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)
from src.engine import minecraft as mc
from src.engine.queries import get_toughness
from .alpha import (
    make_mob,
    make_structure,
    make_tool,
    make_action,
    _attach,
    _cost,
)


# ---------------------------------------------------------------------------
# Effect helpers
# ---------------------------------------------------------------------------

def _opponent(state: GameState, controller: str):
    return next(
        (pid for pid in state.players if pid != controller and not state.players[pid].has_lost),
        None,
    )


def _zone_change(target_id: str, owner: str, from_zone_type: ZoneType, to_zone_type: ZoneType, source_id: str, *, reason: str | None = None) -> Event:
    payload = {
        "object_id": target_id,
        "from_zone_type": from_zone_type,
        "to_zone_type": to_zone_type,
        "from_zone": f"{from_zone_type.name.lower()}_{owner}",
        "to_zone": f"{to_zone_type.name.lower()}_{owner}",
    }
    if reason:
        payload["reason"] = reason
    return Event(type=EventType.ZONE_CHANGE, payload=payload, source=source_id)


def _opp_discard(count: int):
    """Force opp to discard the `count` most-recently-drawn cards from hand.
    We resolve targets at emit time so the queued ZONE_CHANGE events can't
    collide on the same card.
    """
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        hand = state.zones.get(f"hand_{opp}")
        if not hand or not hand.objects:
            return []
        targets = list(hand.objects[-count:])
        return [
            _zone_change(tid, opp, ZoneType.HAND, ZoneType.GRAVEYARD, obj.id, reason="horror_discard")
            for tid in targets
        ]
    return effect


def _opp_mill(count: int):
    """Move the top `count` cards of opp's library to opp's graveyard."""
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        library = state.zones.get(f"library_{opp}")
        if not library or not library.objects:
            return []
        # Library top is conventionally the last item.
        top = list(library.objects[-count:])
        return [
            _zone_change(tid, opp, ZoneType.LIBRARY, ZoneType.GRAVEYARD, obj.id, reason="horror_mill")
            for tid in reversed(top)  # top-of-deck first
        ]
    return effect


def _draw(count: int):
    def effect(obj, state, target_id=None):
        return [Event(type=EventType.DRAW, payload={"player": obj.controller, "count": count}, source=obj.id)]
    return effect


def _heal(amount: int):
    def effect(obj, state, target_id=None):
        return [Event(type=EventType.LIFE_CHANGE, payload={"player": obj.controller, "amount": amount}, source=obj.id)]
    return effect


def _damage_avatar(amount: int):
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={"target": opp, "amount": amount, "source": obj.id, "is_combat": False},
            source=obj.id,
        )]
    return effect


def _damage_target(amount: int):
    """Resolve target_id (action card) to a frontmost grid object or avatar."""
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        target = target_id
        if not target and opp:
            for column in range(mc.GRID_SIZE):
                front = mc.column_target(state, opp, column)
                if front:
                    target = front
                    break
            target = target or opp
        if not target:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={"target": target, "amount": amount, "source": obj.id, "is_combat": False},
            source=obj.id,
        )]
    return effect


def _aoe_enemy_grid(amount: int):
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        events: list[Event] = []
        for row in (state.minecraft_grid.get(opp) or []):
            for oid in row:
                if not oid:
                    continue
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={"target": oid, "amount": amount, "source": obj.id, "is_combat": False},
                    source=obj.id,
                ))
        return events
    return effect


def _aoe_enemy_mobs(amount: int):
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        events: list[Event] = []
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return events
        for oid in list(battlefield.objects):
            o = state.objects.get(oid)
            if not o or o.controller != opp or CardType.MC_MOB not in o.characteristics.types:
                continue
            if o.state.mc_grid_x is not None:
                continue
            events.append(Event(
                type=EventType.DAMAGE,
                payload={"target": oid, "amount": amount, "source": obj.id, "is_combat": False},
                source=obj.id,
            ))
        return events
    return effect


def _wither_storm_play(obj, state, target_id=None):
    """Deal 1 to every opponent mob, structure, and block."""
    return _aoe_enemy_mobs(1)(obj, state, target_id) + _aoe_enemy_grid(1)(obj, state, target_id)


def _destroy_low_hp_mob(threshold: int):
    """Destroy a target mob iff its remaining toughness is <= threshold.
    Wither-style "drag the wounded into the dark" removal.
    """
    def effect(obj, state, target_id=None):
        target = state.objects.get(target_id) if target_id else None
        if not target or CardType.MC_MOB not in target.characteristics.types:
            return []
        remaining = max(0, int(get_toughness(target, state) or 0) - int(target.state.damage or 0))
        if remaining > threshold:
            return []
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={"object_id": target.id, "reason": "horror_drag"},
            source=obj.id,
        )]
    return effect


def _possess_low_hp_mob(threshold: int):
    """Convert a wounded enemy mob to your side, tagging it Horror."""
    def effect(obj, state, target_id=None):
        target = state.objects.get(target_id) if target_id else None
        if not target or CardType.MC_MOB not in target.characteristics.types:
            return []
        if target.controller == obj.controller:
            return []
        remaining = max(0, int(get_toughness(target, state) or 0) - int(target.state.damage or 0))
        if remaining > threshold:
            return []
        target.controller = obj.controller
        target.characteristics.subtypes.add("Horror")
        target.state.summoning_sickness = True
        target.state.tapped = False
        target.state.mc_exhausted = False
        return [Event(
            type=EventType.MC_PLAY_CARD,
            payload={"player": obj.controller, "card_id": obj.id, "kind": "possess", "converted": target.id},
            source=obj.id,
        )]
    return effect


def _grant_keyword_to_target(keyword: str):
    def effect(obj, state, target_id=None):
        target = state.objects.get(target_id) if target_id else None
        if not target or not target.card_def:
            return []
        existing = set(getattr(target.card_def, "mc_keywords", None) or ())
        existing.add(keyword)
        target.card_def.mc_keywords = existing
        return []
    return effect


def _mimic_target_play(obj, state, target_id=None):
    """The Mimicer: gain X/+X where X = power of the target enemy mob."""
    target = state.objects.get(target_id) if target_id else None
    if not target or CardType.MC_MOB not in target.characteristics.types:
        return []
    bonus = max(0, int(target.characteristics.power or 0))
    if bonus <= 0:
        return []
    obj.characteristics.power = int(obj.characteristics.power or 0) + bonus
    obj.characteristics.toughness = int(obj.characteristics.toughness or 0) + bonus
    return []


def _skinwalker_play(obj, state, target_id=None):
    """Skinwalker: copy mc_keywords from target enemy mob (aerial / climb /
    ranged etc.) and steal one of its subtypes for the lord-pattern flavor."""
    target = state.objects.get(target_id) if target_id else None
    if not target or CardType.MC_MOB not in target.characteristics.types:
        return []
    other_kw = set(getattr(target.card_def, "mc_keywords", None) or ())
    if other_kw and obj.card_def is not None:
        existing = set(getattr(obj.card_def, "mc_keywords", None) or ())
        obj.card_def.mc_keywords = existing | other_kw
    # Borrow a non-base subtype so lords on the original tribe sees the copy.
    base = {"Hostile", "Horror", "Stalker", "Boss", "Mob", "Spirit"}
    extras = [s for s in target.characteristics.subtypes if s not in base]
    if extras:
        obj.characteristics.subtypes.add(extras[0])
    return []


# ---------- Hook builders ----------

def _on_attack_chip_avatar(amount: int):
    def hook(obj, state, target_id):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={"target": opp, "amount": amount, "source": obj.id, "is_combat": False},
            source=obj.id,
        )]
    return hook


def _on_attack_discard(count: int):
    def hook(obj, state, target_id):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        hand = state.zones.get(f"hand_{opp}")
        if not hand or not hand.objects:
            return []
        targets = list(hand.objects[-count:])
        return [
            _zone_change(tid, opp, ZoneType.HAND, ZoneType.GRAVEYARD, obj.id, reason="horror_attack_discard")
            for tid in targets
        ]
    return hook


def _on_attack_wither_decay(obj, state, target_id):
    """Wither rot: when this declares an attack against a mob, that mob loses
    1 toughness permanently (mutates obj.characteristics.toughness, which
    get_toughness reads as the base)."""
    target = state.objects.get(target_id) if target_id else None
    if not target or CardType.MC_MOB not in target.characteristics.types:
        return []
    if target.characteristics.toughness is None:
        return []
    target.characteristics.toughness = max(0, int(target.characteristics.toughness) - 1)
    return []


def _on_attack_gain_redstone(obj, state, target_id):
    """Sculk feeds on noise: gain 1 redstone whenever this attacks."""
    return [mc.gain_materials(state, obj.controller, {"redstone": 1})]


def _on_block_sleep(amount: int):
    """Whispering Wraith's defense: chip damage to the attacker."""
    def hook(obj, state, attacker_id):
        if not attacker_id:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={"target": attacker_id, "amount": amount, "source": obj.id, "is_combat": False},
            source=obj.id,
        )]
    return hook


def _on_death_summon(name: str, atk: int, hp: int, subtypes=None, count: int = 1):
    def hook(obj, state):
        return [
            mc.make_minecraft_token(name, obj.controller, atk, hp, set(subtypes or {"Mob", "Horror"}))
            for _ in range(count)
        ]
    return hook


def _on_death_draw_one(obj, state):
    return [Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 1}, source=obj.id)]


def _horror_lord_count(obj, state) -> int:
    """+1 ATK per other Horror you control."""
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return 0
    n = 0
    for oid in battlefield.objects:
        if oid == obj.id:
            continue
        o = state.objects.get(oid)
        if not o or o.controller != obj.controller or not o.card_def:
            continue
        if CardType.MC_MOB in o.characteristics.types and "Horror" in o.characteristics.subtypes:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Card pool
# ---------------------------------------------------------------------------

_cards = [
    # ===================================================================
    # Bosses (8)
    # ===================================================================
    make_mob("The Man From The Fog", 6, 6, _cost(stone=1, iron=2, redstone=1, diamond=1),
             {"Hostile", "Horror", "Stalker", "Boss"},
             "Aerial. When this attacks, deal 2 to defending avatar (a lightning crack from above).",
             mc_keywords={"aerial"},
             on_attack=_on_attack_chip_avatar(2)),
    make_mob("Cave Dweller", 6, 4, _cost(wood=2, iron=2, redstone=1),
             {"Hostile", "Horror", "Stalker", "Boss"},
             "Climb + Haste. When this attacks, opponent discards the most-recent card in hand.",
             keywords={"haste"},
             mc_keywords={"climb"},
             on_attack=_on_attack_discard(1)),
    make_mob("Null, the Empty Skin", 4, 8, _cost(wood=1, stone=1, iron=2, diamond=1),
             {"Hostile", "Horror", "Spirit", "Boss"},
             "Aerial. When played, opponent discards 2.",
             mc_keywords={"aerial"},
             on_play=_opp_discard(2)),
    make_mob("Entity 303", 7, 5, _cost(stone=1, iron=2, redstone=2),
             {"Hostile", "Horror", "Boss"},
             "When played, deal 4 damage to every opponent grid object (a hacker erasing builds).",
             on_play=_aoe_enemy_grid(4)),
    make_mob("Skinwalker, Wearer of Faces", 4, 5, _cost(wood=1, iron=1, redstone=1, diamond=1),
             {"Hostile", "Horror", "Stalker", "Boss"},
             "When played, copy a target enemy mob's keywords and one of its tribal subtypes.",
             on_play=_skinwalker_play),
    make_mob("The Mimicer", 3, 3, _cost(wood=1, iron=1, redstone=1, diamond=1),
             {"Hostile", "Horror", "Stalker", "Boss"},
             "When played, get +X/+X where X is the target enemy mob's printed power.",
             on_play=_mimic_target_play),
    make_mob("Goatman, Crooked Stalker", 5, 5, _cost(wood=2, stone=1, iron=1, redstone=1),
             {"Hostile", "Horror", "Stalker", "Boss", "Beast"},
             "Climb. When this attacks, opponent discards the most-recent card in hand.",
             mc_keywords={"climb"},
             on_attack=_on_attack_discard(1)),
    make_mob("Wither Storm", 10, 8, _cost(stone=1, iron=1, redstone=2, diamond=3),
             {"Hostile", "Horror", "Boss", "Nether"},
             "Aerial. When played, deal 1 to every opponent mob and grid object.",
             mc_keywords={"aerial"},
             on_play=_wither_storm_play),

    # ===================================================================
    # Mid-tier Horrors (~22)
    # ===================================================================
    make_mob("Lost Soul", 1, 1, _cost(wood=1), {"Horror", "Spirit"},
             "Deathrattle: draw a card. \"In life, lost; in death, found.\"",
             on_death=_on_death_draw_one),
    make_mob("Whispering Wraith", 2, 2, _cost(wood=1, stone=1), {"Horror", "Spirit"},
             "Aerial. When this blocks, deal 1 to the attacker.",
             mc_keywords={"aerial"},
             on_block=_on_block_sleep(1)),
    make_mob("Shadow Crawler", 3, 1, _cost(wood=1, stone=1), {"Hostile", "Horror", "Stalker"},
             "Climb. Slips past walls into the columns behind.",
             mc_keywords={"climb"}),
    make_mob("Sleep-Stealer", 2, 3, _cost(wood=2), {"Horror", "Spirit"},
             "Aerial. When played, deal 1 to opponent's avatar.",
             mc_keywords={"aerial"},
             on_play=_damage_avatar(1)),
    make_mob("Dread Husk", 3, 3, _cost(wood=2, stone=1), {"Hostile", "Horror", "Undead"},
             "Hostile. +1 ATK at Night."),
    make_mob("Stray Skeleton", 2, 2, _cost(wood=1, stone=1), {"Hostile", "Horror", "Undead"},
             "Ranged + Reach. Anti-air archer.",
             mc_keywords={"ranged", "reach"}),
    make_mob("Drowned Lurker", 3, 3, _cost(wood=2, stone=1), {"Hostile", "Horror", "Undead"},
             "Ranged. Trident from the depths.",
             mc_keywords={"ranged"}),
    make_mob("Endermite Cluster", 1, 1, _cost(redstone=1), {"Horror", "End"},
             "Deathrattle: summon a 1/1 Endermite token (Horror).",
             on_death=_on_death_summon("Endermite", 1, 1, {"Mob", "Horror", "End"})),
    make_mob("Phantom Wing", 2, 2, _cost(wood=2), {"Hostile", "Horror", "Undead"},
             "Aerial. +1 ATK at Night.",
             mc_keywords={"aerial"}),
    make_mob("Vindicator", 4, 2, _cost(wood=1, stone=1, iron=1), {"Hostile", "Horror", "Raider"},
             "Haste. \"JOHNNY.\"",
             keywords={"haste"}),
    make_mob("Evoker", 3, 3, _cost(wood=1, iron=1, redstone=1), {"Hostile", "Horror", "Raider"},
             "When played, summon a 1/1 Vex token (Aerial, Horror).",
             on_play=lambda obj, state, target_id=None: [
                 mc.make_minecraft_token("Vex", obj.controller, 1, 1, {"Mob", "Horror", "Spirit"})
             ]),
    make_mob("Cave Crawler", 4, 2, _cost(wood=1, stone=1, iron=1), {"Hostile", "Horror", "Stalker"},
             "Climb.",
             mc_keywords={"climb"}),
    make_mob("Wither Skeleton", 4, 3, _cost(stone=1, iron=1, redstone=1), {"Hostile", "Horror", "Nether", "Undead"},
             "Wither rot: when this attacks a mob, that mob permanently loses 1 toughness.",
             on_attack=_on_attack_wither_decay),
    make_mob("Blaze Wraith", 3, 3, _cost(iron=1, redstone=2), {"Hostile", "Horror", "Spirit", "Nether"},
             "Aerial + Ranged.",
             mc_keywords={"aerial", "ranged"}),
    make_mob("Magma Cube Heart", 4, 4, _cost(stone=1, iron=2, redstone=1), {"Hostile", "Horror", "Nether"},
             "Deathrattle: summon two 2/2 Magma Cube tokens.",
             on_death=_on_death_summon("Magma Cube", 2, 2, {"Mob", "Horror", "Nether"}, count=2)),
    make_mob("Silverfish Swarm", 1, 1, _cost(stone=1), {"Hostile", "Horror"},
             "Deathrattle: summon a 1/1 Silverfish token.",
             on_death=_on_death_summon("Silverfish", 1, 1, {"Mob", "Horror"})),
    make_mob("Ratman", 3, 2, _cost(wood=1, stone=1, redstone=1), {"Hostile", "Horror", "Stalker"},
             "Climb. When played, opponent discards 1.",
             mc_keywords={"climb"},
             on_play=_opp_discard(1)),
    make_mob("Backrooms Smiler", 2, 2, _cost(stone=1, redstone=1), {"Hostile", "Horror", "Spirit"},
             "Aerial. Hostile — +1 ATK at Night.",
             mc_keywords={"aerial"}),
    make_mob("Sculk Stalker", 4, 3, _cost(stone=1, iron=1, redstone=1), {"Hostile", "Horror", "Stalker"},
             "When this attacks, gain 1 redstone (sculk feeds on noise).",
             on_attack=_on_attack_gain_redstone),
    make_mob("Elder Phantom", 5, 4, _cost(stone=1, redstone=1, diamond=1), {"Hostile", "Horror", "Undead"},
             "Aerial. When played, opponent discards 1.",
             mc_keywords={"aerial"},
             on_play=_opp_discard(1)),
    make_mob("The Old Watcher", 4, 5, _cost(wood=1, stone=1, iron=1, redstone=1),
             {"Horror", "Boss"},
             "Other Horror mobs you control get +1 ATK.",
             lord_bonus={"subtypes": {"Horror"}, "attack": 1}),
    make_mob("Hollowed Villager", 2, 4, _cost(wood=1, stone=1), {"Horror", "Villager"},
             "Pack of Horror: +1 ATK per other Horror mob you control.",
             dynamic_attack_bonus=_horror_lord_count),

    # ===================================================================
    # Structures + Blocks (~8)
    # ===================================================================
    make_structure("Sculk Catalyst", 3, _cost(stone=1, redstone=1),
                   {"Structure", "Sculk", "Horror"},
                   "Start of turn: gain 1 redstone (sculk grows on every breath).",
                   turn_bonus={"redstone": 1}),
    make_structure("Sculk Shrieker", 4, _cost(stone=1, redstone=1),
                   {"Block", "Sculk", "Horror"},
                   "Wall. The shriek attracts something deep below.",
                   is_block=True),
    make_structure("Lectern of Whispers", 3, _cost(wood=2),
                   {"Structure", "Library", "Horror"},
                   "Start of turn: draw a card.",
                   turn_draw=1),
    make_structure("Cursed Bed", 2, _cost(wood=1),
                   {"Structure", "Bed", "Horror"},
                   "Bed (avatar respawns). Cheap and fragile — easy to break.",
                   ),
    make_structure("Soul Forge", 4, _cost(stone=2),
                   {"Structure", "Forge", "Horror"},
                   "Start of turn: gain 1 iron.",
                   turn_bonus={"iron": 1}),
    make_structure("Eldritch Altar", 4, _cost(wood=1, stone=1, iron=1, redstone=1),
                   {"Structure", "Altar", "Horror"},
                   "Start of turn: gain 1 redstone. When played, draw a card.",
                   turn_bonus={"redstone": 1},
                   on_play=lambda obj, state, target_id=None: [
                       Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 1}, source=obj.id)
                   ]),
    make_structure("Fog Wall", 6, _cost(stone=2),
                   {"Block", "Wall", "Horror"},
                   "Wall variant. The fog hides what's behind.",
                   is_block=True),
    make_structure("Soul Sand Trap", 2, _cost(stone=1, redstone=1),
                   {"Block", "Trap", "Horror"},
                   "Block. Deathrattle: summon a 3/2 Wither Skeleton token.",
                   is_block=True,
                   on_death=_on_death_summon("Wither Skeleton", 3, 2, {"Mob", "Horror", "Undead", "Nether"})),
    make_structure("Stalker's Den", 4, _cost(wood=1, stone=1, redstone=1),
                   {"Structure", "Lair", "Horror"},
                   "Other Stalker mobs you control get +1/+0.",
                   lord_bonus={"subtypes": {"Stalker"}, "attack": 1}),

    # ===================================================================
    # Tools (cursed gear) (~8)
    # ===================================================================
    make_tool("Cursed Pickaxe", "tool", _cost(stone=1, redstone=1),
              "Avatar mines +1 stone and +1 redstone.",
              mining_bonus={"stone": 1, "redstone": 1}),
    make_tool("Eldritch Bow", "weapon", _cost(wood=2, redstone=1),
              "Avatar attack deals 4. Ranged.",
              attack=4, mc_keywords={"ranged"}),
    make_tool("Bone Helm", "armor", _cost(stone=1, iron=1, redstone=1),
              "Avatar takes 2 less damage.",
              armor=2),
    make_tool("Soulstealer Blade", "weapon", _cost(iron=1, diamond=1),
              "Avatar attack deals 5.",
              attack=5),
    make_tool("Wraith Cloak", "armor", _cost(wood=1, redstone=1, diamond=1),
              "Avatar takes 1 less damage. Aerial.",
              armor=1, mc_keywords={"aerial"}),
    make_tool("Reaper's Scythe", "weapon", _cost(iron=2, redstone=1, diamond=1),
              "Avatar attack deals 6. Ranged.",
              attack=6, mc_keywords={"ranged"}),
    make_tool("Skin of the Mimicer", "armor", _cost(wood=1, iron=1, redstone=1),
              "Avatar takes 2 less damage. Climb.",
              armor=2, mc_keywords={"climb"}),
    make_tool("Lantern of the Lost", "tool", _cost(wood=1, redstone=1, diamond=1),
              "Avatar mines +1 diamond.",
              mining_bonus={"diamond": 1}),

    # ===================================================================
    # Actions (~12)
    # ===================================================================
    make_action("Whispering Curse", _cost(redstone=1),
                "Opponent discards the most-recent card in hand.",
                _opp_discard(1)),
    make_action("Drag to the Dark", _cost(wood=1, redstone=1),
                "Destroy a target mob with 3 or fewer remaining HP.",
                _destroy_low_hp_mob(3)),
    make_action("Sleep Deprivation", _cost(wood=1, redstone=1),
                "Deal 2 damage to opponent's avatar; opponent discards 1.",
                lambda obj, state, target_id=None: (
                    _damage_avatar(2)(obj, state, target_id)
                    + _opp_discard(1)(obj, state, target_id)
                )),
    make_action("Suspicious Stew", _cost(wood=1),
                "Heal your avatar 4.",
                _heal(4)),
    make_action("Wither Skull", _cost(stone=1, redstone=1),
                "Deal 3 damage to a target.",
                _damage_target(3)),
    make_action("Possession", _cost(iron=1, redstone=1),
                "Take control of a target enemy mob with 2 or fewer remaining HP; it joins your side as a Horror.",
                _possess_low_hp_mob(2)),
    make_action("Eldritch Insight", _cost(redstone=1),
                "Draw 2 cards.",
                _draw(2)),
    make_action("Fog Roll", _cost(wood=1, stone=1),
                "Grant a target one of your mobs Climb permanently.",
                _grant_keyword_to_target("climb")),
    make_action("Skinwalker Trick", _cost(wood=1, redstone=1),
                "Summon a 3/3 Horror token (Stalker).",
                lambda obj, state, target_id=None: [
                    mc.make_minecraft_token("Skinwalker Husk", obj.controller, 3, 3,
                                            {"Mob", "Horror", "Stalker", "Hostile"})
                ]),
    make_action("The Wither Calls", _cost(stone=1, iron=1, redstone=1),
                "Deal 3 to every opponent mob.",
                _aoe_enemy_mobs(3)),
    make_action("Phantom Flock", _cost(wood=1, iron=1, redstone=1),
                "Summon two 2/2 Phantom tokens (Aerial, Horror).",
                lambda obj, state, target_id=None: [
                    mc.make_minecraft_token("Phantom", obj.controller, 2, 2,
                                            {"Mob", "Horror", "Undead"}),
                    mc.make_minecraft_token("Phantom", obj.controller, 2, 2,
                                            {"Mob", "Horror", "Undead"}),
                ]),
    make_action("The Cave Calls", _cost(wood=1, stone=1, redstone=1),
                "Summon a 4/2 Cave Crawler token (Climb, Hostile, Horror).",
                lambda obj, state, target_id=None: [
                    mc.make_minecraft_token("Cave Crawler", obj.controller, 4, 2,
                                            {"Mob", "Horror", "Stalker", "Hostile"})
                ]),
    make_action("Backrooms Trip", _cost(stone=1, redstone=1),
                "Mill the top 3 cards of opponent's library.",
                _opp_mill(3)),
    make_action("Bloodmoon Ritual", _cost(iron=1, redstone=1),
                "Grant a target one of your mobs Aerial permanently.",
                _grant_keyword_to_target("aerial")),
    make_action("Goatman's Hex", _cost(wood=1, redstone=1),
                "Deal 1 damage to every opponent mob.",
                _aoe_enemy_mobs(1)),
]


HORROR_CARDS = {card.name: card for card in _cards}
