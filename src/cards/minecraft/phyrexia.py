"""Phyrexia Bedrock Edition — Phyrexian-themed Minecraft TCG expansion.

A Phyrexian invasion has compleated the Bedrock layer of the Overworld through
the Realmbreaker. Cards here introduce three new mechanics:

  - Compleated subtype: mob is stronger, but at start of your turn each
    Compleated mob you control deals 1 damage to your avatar.
  - Infect keyword (mc_keywords): combat damage to the avatar also deposits
    oil counters; reach 5 oil counters and the player loses outright.
  - Glistening Oil: action card that flips a low-HP enemy mob to your side
    as Compleated.

Set design balances around the workers-into-bombs ramp deck the Alpha set
encourages: Phyrexia adds cheap aggression (Negator, Carnophage, Plague Myr),
single-target removal (Herobrine, Disfigure, Putrefy), board sweepers
(Sickening Dreams, Phyrexian Rebirth, Toxic Deluge), and drain control
(Sheoldred, Sangromancer).
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
from .alpha import (
    make_mob,
    make_structure,
    make_tool,
    make_action,
    _attach,
    _cost,
    _on_death_column_blast,
)


# ---------------------------------------------------------------------------
# Effect helpers — Phyrexian flavors
# ---------------------------------------------------------------------------

def _opponent(state: GameState, controller: str):
    return next((pid for pid in state.players if pid != controller and not state.players[pid].has_lost), None)


def _drain(amount: int):
    """Deal `amount` to opponent's avatar; heal that much to you. The
    LIFE_CHANGE pipeline handler respects the mode's life_cap."""
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        return [
            Event(type=EventType.DAMAGE, payload={"target": opp, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={"player": obj.controller, "amount": amount}, source=obj.id),
        ]
    return effect


def _gain_all_materials(amount: int):
    def effect(obj, state, target_id=None):
        gains = {m: amount for m in mc.MATERIALS}
        return [mc.gain_materials(state, obj.controller, gains)]
    return effect


def _gain_material(material: str, amount: int):
    def effect(obj, state, target_id=None):
        return [mc.gain_materials(state, obj.controller, {material: amount})]
    return effect


def _draw(count: int):
    def effect(obj, state, target_id=None):
        return [Event(type=EventType.DRAW, payload={"player": obj.controller, "count": count}, source=obj.id)]
    return effect


def _heal(amount: int):
    def effect(obj, state, target_id=None):
        return [Event(type=EventType.LIFE_CHANGE, payload={"player": obj.controller, "amount": amount}, source=obj.id)]
    return effect


def _aoe_enemy_grid(amount: int):
    """Deal damage to every opponent grid object."""
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        events = []
        grid = state.minecraft_grid.get(opp) or []
        for row in grid:
            for oid in row:
                if not oid:
                    continue
                events.append(Event(type=EventType.DAMAGE, payload={"target": oid, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id))
        return events
    return effect


def _aoe_enemy_mobs(amount: int):
    """Deal damage to every opponent mob in the battle row."""
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        events = []
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return events
        for oid in list(battlefield.objects):
            o = state.objects.get(oid)
            if not o or o.controller != opp or CardType.MC_MOB not in o.characteristics.types:
                continue
            if o.state.mc_grid_x is not None:  # skip on-grid
                continue
            events.append(Event(type=EventType.DAMAGE, payload={"target": oid, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id))
        return events
    return effect


def _aoe_all_mobs(amount: int):
    """Deal damage to every mob in the battle row, both players."""
    def effect(obj, state, target_id=None):
        events = []
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return events
        for oid in list(battlefield.objects):
            o = state.objects.get(oid)
            if not o or CardType.MC_MOB not in o.characteristics.types:
                continue
            if o.state.mc_grid_x is not None:
                continue
            events.append(Event(type=EventType.DAMAGE, payload={"target": oid, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id))
        return events
    return effect


def _sweep_destroy_mobs():
    """Phyrexian Rebirth: destroy every mob in the battle row, both players."""
    def effect(obj, state, target_id=None):
        events = []
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return events
        for oid in list(battlefield.objects):
            o = state.objects.get(oid)
            if not o or CardType.MC_MOB not in o.characteristics.types:
                continue
            if o.state.mc_grid_x is not None:
                continue
            events.append(Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": oid, "reason": "rebirth"}, source=obj.id))
        # Spawn a compensation 4/4 Horror token for the caster.
        events.append(mc.make_minecraft_token("Phyrexian Horror", obj.controller, 4, 4, {"Hostile", "Mob", "Compleated"}))
        return events
    return effect


def _glistening_oil(obj, state, target_id=None):
    """Convert opponent mob with HP <= 2 to your side as Compleated."""
    if not target_id:
        return []
    if mc.glistening_oil_convert(state, obj.controller, target_id):
        return [Event(type=EventType.MC_PLAY_CARD, payload={"player": obj.controller, "card_id": obj.id, "kind": "glistening_oil", "converted": target_id}, source=obj.id)]
    return []


def _compleat_target(obj, state, target_id=None):
    """Add Compleated subtype to one of your mobs (and +1 ATK via the lord
    pattern on the card itself)."""
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.controller != obj.controller:
        return []
    if CardType.MC_MOB not in target.characteristics.types:
        return []
    target.characteristics.subtypes.add("Compleated")
    return []


def _mass_compleat(obj, state, target_id=None):
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    for oid in list(battlefield.objects):
        o = state.objects.get(oid)
        if not o or o.controller != obj.controller or CardType.MC_MOB not in o.characteristics.types:
            continue
        o.characteristics.subtypes.add("Compleated")
    return []


def _destroy_mob(obj, state, target_id=None):
    """Single-target mob removal (Herobrine, Putrefy, Disfigure-ish)."""
    target = state.objects.get(target_id) if target_id else None
    if not target:
        return []
    if CardType.MC_MOB not in target.characteristics.types:
        return []
    return [Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": target_id, "reason": "removal"}, source=obj.id)]


def _damage_target(amount: int):
    def effect(obj, state, target_id=None):
        opp = _opponent(state, obj.controller)
        target = target_id
        if not target:
            for column in range(mc.GRID_SIZE):
                front = mc.column_target(state, opp, column) if opp else None
                if front:
                    target = front
                    break
            target = target or opp
        if not target:
            return []
        return [Event(type=EventType.DAMAGE, payload={"target": target, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id)]
    return effect


def _reanimate(obj, state, target_id=None):
    """Move a Compleated mob from your graveyard to the battlefield."""
    if not target_id:
        return []
    graveyard = state.zones.get(f"graveyard_{obj.controller}")
    target = state.objects.get(target_id)
    if not graveyard or not target or target_id not in graveyard.objects:
        return []
    if CardType.MC_MOB not in target.characteristics.types:
        return []
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": target_id,
            "from_zone_type": ZoneType.GRAVEYARD,
            "to_zone_type": ZoneType.BATTLEFIELD,
            "from_zone": f"graveyard_{obj.controller}",
            "to_zone": "battlefield",
        },
        source=obj.id,
    )]


def _yawgmoths_will(obj, state, target_id=None):
    """Cast an action from your graveyard for free (replay)."""
    if not target_id:
        return []
    graveyard = state.zones.get(f"graveyard_{obj.controller}")
    target = state.objects.get(target_id)
    if not graveyard or not target or target_id not in graveyard.objects:
        return []
    if CardType.MC_ACTION not in target.characteristics.types:
        return []
    on_play = getattr(target.card_def, "mc_on_play", None) if target.card_def else None
    events = []
    if callable(on_play):
        events.extend(on_play(target, state) or [])
    return events


def _toxic_deluge(amount: int):
    """Deal `amount` damage to every mob (yours and opponents'). Caster pays
    `amount` HP to use this raw power."""
    def effect(obj, state, target_id=None):
        you = state.players.get(obj.controller)
        events = []
        if you and you.life > amount:
            you.life -= amount
            events.append(Event(type=EventType.LIFE_CHANGE, payload={"player": obj.controller, "amount": -amount, "new_life": you.life}, source=obj.id))
        events.extend(_aoe_all_mobs(amount)(obj, state, target_id))
        return events
    return effect


# Praetor on_play helpers
def _elesh_norn_play(obj, state, target_id=None):
    """Deal 2 damage to every enemy mob in battle row."""
    return _aoe_enemy_mobs(2)(obj, state, target_id)


def _yawgmoth_play(obj, state, target_id=None):
    """Deal 4 to every opponent mob and grid object."""
    return _aoe_enemy_mobs(4)(obj, state, target_id) + _aoe_enemy_grid(4)(obj, state, target_id)


def _vorinclex_play(obj, state, target_id=None):
    return [mc.gain_materials(state, obj.controller, {m: 1 for m in mc.MATERIALS})]


def _herobrine_play(obj, state, target_id=None):
    """Destroy any 1 mob (target). 'This is _my_ world.'"""
    return _destroy_mob(obj, state, target_id)


def _atraxa_play(obj, state, target_id=None):
    return [mc.gain_materials(state, obj.controller, {m: 1 for m in mc.MATERIALS}), Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 2}, source=obj.id)]


def _on_attack_burn(amount: int):
    def hook(obj, state, target_id):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        return [Event(type=EventType.DAMAGE, payload={"target": opp, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id)]
    return hook


def _negator_on_damage(obj, state, amount):
    """Whenever this is dealt damage: sacrifice another mob you control.
    If you control no other mobs, this is destroyed.
    Classic Phyrexian Negator: a 5/5 for 2 wood that exacts a price every
    time it's hit, even by a chip.
    """
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    sacrifice = None
    for oid in battlefield.objects:
        if oid == obj.id:
            continue
        o = state.objects.get(oid)
        if not o or o.controller != obj.controller:
            continue
        if CardType.MC_MOB not in o.characteristics.types:
            continue
        # Prefer the cheapest body to absorb the cost.
        if sacrifice is None or int(o.characteristics.toughness or 0) < int(sacrifice.characteristics.toughness or 0):
            sacrifice = o
    if sacrifice is not None:
        return [Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": sacrifice.id, "reason": "negator_sacrifice"}, source=obj.id)]
    # No sacrifice available — Negator destroys itself.
    return [Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": obj.id, "reason": "negator_self"}, source=obj.id)]


def _sangromancer_on_play(obj, state, target_id=None):
    """When played: heal 4 to your avatar (representing draining souls of fallen)."""
    return _heal(4)(obj, state, target_id)


# ---------------------------------------------------------------------------
# Card pool
# ---------------------------------------------------------------------------

_cards = [
    # ===================================================================
    # 8 marquee bosses
    # ===================================================================
    make_mob("Elesh Norn, Grand Cenobite", 6, 9, _cost(iron=3, redstone=1, diamond=2),
             {"Hostile", "Boss", "Praetor", "Compleated"},
             "Other Compleated mobs you control get +1 ATK. When played, deal 2 to every enemy mob.",
             lord_bonus={"subtypes": {"Compleated"}, "attack": 1},
             on_play=_elesh_norn_play),
    make_mob("Sheoldred, the Whispering One", 5, 8, _cost(wood=1, iron=2, redstone=2),
             {"Hostile", "Boss", "Praetor", "Compleated"},
             "When played, drain 5 (deal 5 to opponent, heal 5).",
             on_play=_drain(5)),
    make_mob("Vorinclex, Voice of Hunger", 7, 9, _cost(wood=3, iron=2, redstone=1),
             {"Hostile", "Boss", "Praetor", "Compleated"},
             "Reach. When played, gain 1 of every material.",
             mc_keywords={"reach"},
             on_play=_vorinclex_play),
    make_mob("Urabrask, the Heretic", 5, 5, _cost(stone=2, redstone=2, iron=1),
             {"Hostile", "Boss", "Praetor", "Compleated"},
             "Haste. Other Hostile mobs you control have Haste. On attack, deal 1 to opponent.",
             keywords={"haste"},
             lord_bonus={"subtypes": {"Hostile"}, "attack": 1},
             on_attack=_on_attack_burn(1)),
    make_mob("Jin-Gitaxias, Core Augur", 5, 7, _cost(redstone=3, diamond=2),
             {"Hostile", "Boss", "Praetor", "Compleated"},
             "Aerial. When played, draw 3.",
             mc_keywords={"aerial"},
             on_play=_draw(3)),
    make_mob("Atraxa, Grand Unifier", 7, 8, _cost(wood=1, iron=2, redstone=2, diamond=2),
             {"Hostile", "Boss", "Praetor", "Compleated"},
             "Aerial + Reach. When played, gain 1 of every material and draw 2.",
             mc_keywords={"aerial", "reach"},
             on_play=_atraxa_play),
    make_mob("Yawgmoth, Father of Machines", 9, 9, _cost(stone=2, iron=3, redstone=3, diamond=2),
             {"Hostile", "Boss", "Compleated"},
             "When played, deal 4 to every enemy mob and every enemy grid object.",
             on_play=_yawgmoth_play),
    # Herobrine is a one-shot ritual, not a mob — he is the world.
    make_action("Herobrine, World's Eye", _cost(redstone=2, diamond=2),
                "Destroy any 1 mob. \"This is _my_ world.\"",
                _herobrine_play),

    # ===================================================================
    # ~25 Compleated mobs — including Compleated versions of alpha mobs
    # ===================================================================

    # Cheap aggression
    make_mob("Phyrexian Walker", 1, 3, _cost(stone=1), {"Compleated"},
             "Compleated. Cheap chump that dies for the cause."),
    make_mob("Carnophage", 2, 2, _cost(wood=1), {"Hostile", "Compleated"},
             "Compleated. Hostile. +1 ATK at Night."),
    make_mob("Plague Myr", 1, 1, _cost(wood=1), {"Compleated"},
             "Compleated. Infect.",
             mc_keywords={"infect"}),
    make_mob("Glistening Mite", 2, 1, _cost(wood=1), {"Hostile", "Compleated"},
             "Compleated. Infect.",
             mc_keywords={"infect"}),
    _attach(
        make_mob("Phyrexian Negator", 5, 5, _cost(wood=2), {"Hostile", "Compleated"},
                 "Compleated. Whenever this is dealt damage, sacrifice another mob you control. If you can't, destroy this.",
                 ),
        mc_on_damage=_negator_on_damage,
    ),

    # Mid-tier
    make_mob("Phyrexian Crusader", 3, 3, _cost(wood=1, iron=2), {"Hostile", "Compleated"},
             "Compleated. Aerial + Infect.",
             mc_keywords={"aerial", "infect"}),
    make_mob("Glissa, the Traitor", 3, 3, _cost(wood=1, iron=1, redstone=1),
             {"Hostile", "Compleated"},
             "Compleated. When this kills a mob in combat, draw a card.",
             on_attack=lambda obj, state, target_id: [Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 1}, source=obj.id)] if target_id and target_id in state.objects else []),
    make_mob("Sangromancer", 3, 3, _cost(iron=1, redstone=1), {"Compleated"},
             "Compleated. When played, heal 4 (from draining the fallen).",
             on_play=_sangromancer_on_play),
    make_mob("Phyrexian Tyranny", 4, 3, _cost(iron=2), {"Hostile", "Compleated"},
             "Compleated. Hostile."),
    make_mob("Hex Parasite", 3, 3, _cost(redstone=2), {"Compleated"},
             "Compleated. When played, deal 2 damage to any 1 mob.",
             on_play=_destroy_mob),
    make_mob("K'rrik, Son of Yawgmoth", 4, 4, _cost(iron=2, redstone=1), {"Hostile", "Compleated"},
             "Compleated. Reach. Late-game grinder.",
             mc_keywords={"reach"}),
    make_mob("Skithiryx, the Blight Dragon", 5, 5, _cost(redstone=2, diamond=1, iron=1),
             {"Hostile", "Boss", "Compleated"},
             "Compleated. Aerial + Infect + Haste.",
             keywords={"haste"},
             mc_keywords={"aerial", "infect"}),
    make_mob("Vorinclex's Spawn", 4, 6, _cost(wood=2, redstone=1), {"Hostile", "Compleated"},
             "Compleated."),
    make_mob("Mycoid Shepherd", 4, 4, _cost(wood=2, stone=1), {"Compleated"},
             "Compleated. When played, heal 4.",
             on_play=_heal(4)),
    make_mob("Phyrexian Obliterator", 5, 5, _cost(iron=2, redstone=2),
             {"Hostile", "Compleated"},
             "Compleated. Hostile. Hard to remove."),
    make_mob("Inkmoth Nexus", 1, 1, _cost(wood=1), {"Compleated"},
             "Compleated. Infect.",
             mc_keywords={"infect"}),
    make_mob("Phyrexian Mycoderm", 3, 4, _cost(wood=1, stone=2), {"Compleated"},
             "Compleated. Reach (anti-air with mushroom spores).",
             mc_keywords={"reach"}),
    make_mob("Geth, Lord of the Vault", 4, 5, _cost(wood=1, iron=2),
             {"Hostile", "Boss", "Compleated"},
             "Compleated. When played, gain 2 redstone.",
             on_play=_gain_material("redstone", 2)),
    make_mob("Tyrant of Kher Ridges", 5, 5, _cost(stone=2, redstone=2),
             {"Hostile", "Compleated"},
             "Compleated. When played, deal 2 to all enemy mobs.",
             on_play=_aoe_enemy_mobs(2)),

    # Compleated versions of alpha mobs
    make_mob("Compleated Steve", 2, 3, _cost(wood=2), {"Worker", "Compleated"},
             "Compleated worker. Mining yields +1 wood.",
             mining_bonus={"wood": 1}),
    make_mob("Compleated Villager", 2, 2, _cost(wood=1), {"Villager", "Worker", "Compleated"},
             "Compleated worker. Mining yields +1 stone.",
             mining_bonus={"stone": 1}),
    make_mob("Compleated Wolf Pack", 4, 3, _cost(wood=1, iron=2), {"Animal", "Compleated"},
             "Compleated. Pack: +1 ATK per other Worker you control.",
             dynamic_attack_bonus=lambda obj, state: sum(
                 1 for oid in (state.zones.get("battlefield").objects if state.zones.get("battlefield") else [])
                 if oid != obj.id
                 and (o := state.objects.get(oid))
                 and o.controller == obj.controller
                 and o.card_def
                 and CardType.MC_MOB in o.characteristics.types
                 and "Worker" in o.characteristics.subtypes
             )),
    make_mob("Compleated Iron Golem", 6, 6, _cost(iron=3, redstone=2), {"Golem", "Compleated"},
             "Compleated. Massive body."),
    make_mob("Compleated Creeper", 5, 2, _cost(stone=2), {"Hostile", "Compleated"},
             "Compleated. Deathrattle: deal 4 to the frontmost in the column it attacked.",
             on_death=_on_death_column_blast(4)),
    make_mob("Compleated Spider", 3, 4, _cost(wood=1, stone=1), {"Hostile", "Compleated"},
             "Compleated. Climb + Infect.",
             mc_keywords={"climb", "infect"}),
    make_mob("Compleated Skeleton", 4, 2, _cost(wood=1, stone=1),
             {"Hostile", "Undead", "Compleated"},
             "Compleated. Ranged + Reach.",
             mc_keywords={"ranged", "reach"}),
    make_mob("Compleated Enderman", 5, 5, _cost(iron=2, redstone=1),
             {"Hostile", "End", "Compleated"},
             "Compleated. Aerial.",
             mc_keywords={"aerial"}),
    make_mob("Compleated Wither", 8, 7, _cost(redstone=3, diamond=2),
             {"Hostile", "Boss", "Nether", "Compleated"},
             "Compleated. When played, deal 3 to every opponent grid object.",
             on_play=_aoe_enemy_grid(3)),
    make_mob("Compleated Ender Dragon", 10, 10, _cost(redstone=2, diamond=4),
             {"Hostile", "Boss", "End", "Compleated"},
             "Compleated. Aerial + Infect.",
             mc_keywords={"aerial", "infect"}),

    # ===================================================================
    # ~12 Phyrexian structures / blocks
    # ===================================================================
    make_structure("Mycosynth Garden", 4, _cost(stone=2, redstone=1),
                   {"Structure", "Mycosynth"},
                   "Start of turn: gain 1 wood and 1 redstone.",
                   turn_bonus={"wood": 1, "redstone": 1}),
    make_structure("Phyrexian Arena", 5, _cost(wood=2, iron=1),
                   {"Structure", "Arena"},
                   "Start of turn: draw a card.",
                   turn_draw=1),
    make_structure("Oil Refinery", 4, _cost(stone=2, iron=1),
                   {"Structure", "Refinery"},
                   "Start of turn: gain 1 redstone.",
                   turn_bonus={"redstone": 1}),
    make_structure("Realmbreaker Spire", 8, _cost(stone=3, diamond=2),
                   {"Structure", "Spire"},
                   "Start of turn: gain 1 of every material.",
                   turn_bonus={"wood": 1, "stone": 1, "iron": 1, "redstone": 1, "diamond": 1}),
    make_structure("Cranial Plating Workshop", 4, _cost(stone=2),
                   {"Structure", "Forge"},
                   "Foundry support — production line for Phyrexian gear."),
    make_structure("Phyrexian Pylon", 3, _cost(wood=1, redstone=1),
                   {"Block", "Pylon"},
                   "Start of turn: gain 1 redstone.",
                   is_block=True,
                   turn_bonus={"redstone": 1}),
    make_structure("Sludge Strider Hive", 4, _cost(wood=1, redstone=1),
                   {"Structure", "Hive"},
                   "Start of turn: produce 1 wood (sludge from the hive walls).",
                   turn_bonus={"wood": 1}),
    make_structure("Throne of Geth", 3, _cost(wood=1, stone=1),
                   {"Structure", "Throne"},
                   "Foul artifact pulpit."),
    make_structure("Phyrexian Tower", 5, _cost(stone=2, iron=1),
                   {"Structure", "Tower"},
                   "When played, gain 2 iron.",
                   on_play=_gain_material("iron", 2)),
    make_structure("Lattice of Steel", 4, _cost(iron=2),
                   {"Block", "Wall", "Lattice"},
                   "Wall variant. Other Phyrexian structures gain +1 ATK to your mobs (Compleated lord).",
                   is_block=True,
                   lord_bonus={"subtypes": {"Compleated"}, "attack": 1}),
    make_structure("Glistening Pool", 3, _cost(wood=1),
                   {"Block", "Trap"},
                   "Block. Deathrattle: opponent gains 1 oil counter.",
                   is_block=True,
                   on_death=lambda obj, state: (
                       [Event(type=EventType.DAMAGE, payload={"target": _opponent(state, obj.controller), "amount": 0, "infect_counters": 1}, source=obj.id)]
                       if (opp := _opponent(state, obj.controller)) and (state.players[opp].__setattr__("mc_oil_counters", (getattr(state.players[opp], "mc_oil_counters", 0) or 0) + 1) or True)
                       else []
                   )),
    make_structure("Mycosynth Wellspring", 3, _cost(redstone=1),
                   {"Structure", "Mycosynth"},
                   "When played, gain 1 redstone and draw 1.",
                   on_play=lambda obj, state, target_id=None: [
                       mc.gain_materials(state, obj.controller, {"redstone": 1}),
                       Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 1}, source=obj.id),
                   ]),

    # ===================================================================
    # ~10 Phyrexian tools (gear)
    # ===================================================================
    make_tool("Cranial Plating", "tool", _cost(iron=2),
              "Avatar's mining is sharper.",
              mining_bonus={"iron": 1}),
    make_tool("Phyrexian Sword", "weapon", _cost(iron=1, redstone=1),
              "Avatar attack deals 5. Infect.",
              attack=5, mc_keywords={"infect"}),
    make_tool("Skinrender Greaves", "armor", _cost(iron=2, redstone=1),
              "Avatar takes 3 less damage.",
              armor=3),
    make_tool("Glistening Cloak", "armor", _cost(redstone=1, diamond=1),
              "Avatar takes 2 less damage. Aerial.",
              armor=2, mc_keywords={"aerial"}),
    make_tool("Sword of the Compleat", "weapon", _cost(iron=2, diamond=1),
              "Avatar attack deals 6. Aerial.",
              attack=6, mc_keywords={"aerial"}),
    make_tool("Praetor's Crown", "tool", _cost(redstone=2, diamond=1),
              "Avatar mines +1 diamond.",
              mining_bonus={"diamond": 1}),
    make_tool("Phyrexian Pickaxe", "tool", _cost(iron=1, stone=1),
              "Avatar mines +2 stone.",
              mining_bonus={"stone": 2}),
    make_tool("Mycosynth Bracers", "tool", _cost(stone=1, redstone=1),
              "Avatar mines +1 redstone.",
              mining_bonus={"redstone": 1}),
    make_tool("Carrion Sword", "weapon", _cost(wood=1, stone=1),
              "Avatar attack deals 3.",
              attack=3),
    make_tool("Throne Helm", "armor", _cost(iron=2),
              "Avatar takes 3 less damage.",
              armor=3),

    # ===================================================================
    # ~25 Phyrexian actions
    # ===================================================================
    make_action("Glistening Oil", _cost(redstone=2),
                "Compleate target enemy mob with HP ≤ 2 — it joins your side.",
                _glistening_oil),
    make_action("Sickening Dreams", _cost(redstone=2),
                "Deal 2 to every mob (yours and opponents').",
                _aoe_all_mobs(2)),
    make_action("Phyrexian Rebirth", _cost(stone=1, iron=2, redstone=2),
                "Destroy every mob in the battle row, then create a 4/4 Phyrexian Horror.",
                _sweep_destroy_mobs()),
    make_action("Sheoldred's Restoration", _cost(redstone=1),
                "Heal 5 to your avatar and draw a card.",
                lambda obj, state, target_id=None: _heal(5)(obj, state, target_id) + _draw(1)(obj, state, target_id)),
    make_action("Surgical Extraction", _cost(redstone=1),
                "Banish a card from a graveyard (precision strike).",
                _draw(1)),  # simplified — just card draw flavor
    make_action("Disfigure", _cost(wood=1),
                "Deal 3 damage to a target mob.",
                _damage_target(3)),
    make_action("Toxic Deluge", _cost(stone=1, redstone=1, iron=1),
                "Pay 3 HP. Deal 3 to every mob.",
                _toxic_deluge(3)),
    make_action("Phyrexian Vault", _cost(stone=1),
                "Gain 2 redstone.",
                _gain_material("redstone", 2)),
    make_action("Yawgmoth's Mandate", _cost(wood=1, iron=1),
                "Gain 1 of every material.",
                _gain_all_materials(1)),
    make_action("Yawgmoth's Will", _cost(redstone=2, diamond=1),
                "Replay a target action card from your graveyard.",
                _yawgmoths_will),
    make_action("Reanimate", _cost(wood=1, redstone=1),
                "Return a target Compleated mob from your graveyard to play.",
                _reanimate),
    make_action("Compulsive Research", _cost(redstone=2),
                "Draw 3 cards.",
                _draw(3)),
    make_action("Compleat", _cost(redstone=1),
                "Add the Compleated subtype to one of your mobs.",
                _compleat_target),
    make_action("Mass Compleation", _cost(redstone=2, diamond=1),
                "All your mobs become Compleated.",
                _mass_compleat),
    make_action("Cremate", _cost(stone=1),
                "Banish a card from a graveyard, draw a card.",
                _draw(1)),
    make_action("Massacre", _cost(wood=1, redstone=2),
                "Deal 3 to every opponent mob.",
                _aoe_enemy_mobs(3)),
    make_action("Black Sun's Zenith", _cost(redstone=2),
                "Deal 4 to every mob (yours and opponents').",
                _aoe_all_mobs(4)),
    make_action("Inkmoth Surge", _cost(wood=1),
                "Add Infect to one of your mobs (permanent).",
                lambda obj, state, target_id=None: (
                    _add_keyword_to(target_id, state, "infect") if target_id else []
                )),
    make_action("Putrefy", _cost(wood=1, iron=1),
                "Destroy a target mob.",
                _destroy_mob),
    make_action("Praetor's Bounty", _cost(stone=1),
                "Gain 3 wood.",
                _gain_material("wood", 3)),
    make_action("Despise", _cost(wood=1),
                "Look at opponent's hand and discard the most expensive card.",
                _draw(1)),  # simplified
    make_action("Voltage Surge", _cost(redstone=1),
                "Deal 2 damage to a target.",
                _damage_target(2)),
    make_action("Realmbreaker's Reach", _cost(stone=1, redstone=1),
                "Gain 1 of every material.",
                _gain_all_materials(1)),
    make_action("Praetor's Grasp", _cost(redstone=2, diamond=1),
                "Search opponent's library for a card and exile it (simplified: draw 2).",
                _draw(2)),
    make_action("Annihilator Symbol", _cost(stone=1),
                "Gain 5 of any material (caster picks redstone by default).",
                _gain_material("redstone", 5)),
]


def _add_keyword_to(target_id: str, state: GameState, keyword: str) -> list[Event]:
    target = state.objects.get(target_id)
    if not target or not target.card_def:
        return []
    existing = set(getattr(target.card_def, "mc_keywords", None) or ())
    existing.add(keyword)
    target.card_def.mc_keywords = existing
    return []


PHYREXIA_CARDS = {card.name: card for card in _cards}
