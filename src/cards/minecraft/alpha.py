"""Minecraft TCG alpha cards and starter decks.

Card model:
    - Mobs live in the battlefield row; can mine (if Worker subtype) or attack.
    - Structures + Blocks live on a 3x3 grid; attacks resolve column-by-column.
    - Tools attach to the Avatar (weapon / armor / tool slot).
    - Actions resolve from hand to graveyard.

Available card hooks (all optional, attached via _attach):
    mc_keywords          set of: aerial, climb, siege, ranged, haste
    mc_on_play(obj, state, target_id)            -> list[Event]
    mc_on_attack(obj, state, target_id)          -> list[Event]
    mc_on_block(obj, state, attacker_id)         -> list[Event]
    mc_on_death(obj, state)                      -> list[Event]
    mc_lord_bonus  = {"subtypes": {...}, "attack": int, "toughness": int}
    mc_dynamic_attack_bonus(obj, state)          -> int
    mc_turn_bonus  = {"wood": 1, ...}            applied on turn start
    mc_turn_draw   = int                         applied on turn start
    mc_mining_bonus = dict | str                 extra mining yield
    mc_tool_slot    = "weapon" | "armor" | "tool"
    mc_attack       = int    (Avatar damage when this weapon is equipped)
    mc_armor        = int    (description-only for now)
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


# ---------------------------------------------------------------------------
# Card factories
# ---------------------------------------------------------------------------

def _cost(**kwargs) -> dict[str, int]:
    return {m: int(kwargs.get(m, 0) or 0) for m in mc.MATERIALS if int(kwargs.get(m, 0) or 0) > 0}


def _attach(card: CardDefinition, **attrs) -> CardDefinition:
    for key, value in attrs.items():
        if value is None:
            continue
        setattr(card, key, value)
    return card


def make_mob(
    name: str,
    attack: int,
    health: int,
    cost: dict[str, int],
    subtypes=None,
    text: str = "",
    *,
    mining_bonus=None,
    keywords=None,           # engine keywords like "haste"
    mc_keywords=None,        # minecraft-only: aerial, climb, siege, ranged
    on_play=None,
    on_attack=None,
    on_block=None,
    on_death=None,
    on_event=None,           # generic listener: fn(obj, state, event) -> list[Event]
    lord_bonus=None,
    dynamic_attack_bonus=None,
):
    abilities = [{"keyword": k} for k in (keywords or set())]
    card = CardDefinition(
        name=name,
        mana_cost=None,
        domain="MC",
        text=text,
        characteristics=Characteristics(
            types={CardType.MC_MOB},
            subtypes=set(subtypes or {"Mob"}),
            power=attack,
            toughness=health,
            abilities=abilities,
        ),
    )
    return _attach(
        card,
        mc_cost=cost,
        mc_mining_bonus=mining_bonus,
        mc_keywords=set(mc_keywords) if mc_keywords else None,
        mc_on_play=on_play,
        mc_on_attack=on_attack,
        mc_on_block=on_block,
        mc_on_death=on_death,
        mc_on_event=on_event,
        mc_lord_bonus=lord_bonus,
        mc_dynamic_attack_bonus=dynamic_attack_bonus,
    )


def make_structure(
    name: str,
    durability: int,
    cost: dict[str, int],
    subtypes=None,
    text: str = "",
    *,
    is_block: bool = False,
    turn_bonus: dict[str, int] | None = None,
    turn_draw: int = 0,
    on_play=None,
    on_death=None,
    lord_bonus=None,
):
    card_type = CardType.MC_BLOCK if is_block else CardType.MC_STRUCTURE
    card = CardDefinition(
        name=name,
        mana_cost=None,
        domain="MC",
        text=text,
        characteristics=Characteristics(
            types={card_type},
            subtypes=set(subtypes or {"Structure"}),
            toughness=durability,
        ),
    )
    return _attach(
        card,
        mc_cost=cost,
        mc_turn_bonus=turn_bonus or {},
        mc_turn_draw=turn_draw,
        mc_on_play=on_play,
        mc_on_death=on_death,
        mc_lord_bonus=lord_bonus,
    )


def make_tool(
    name: str,
    slot: str,
    cost: dict[str, int],
    text: str = "",
    *,
    attack: int = 0,
    armor: int = 0,
    mining_bonus=None,
    mc_keywords=None,
):
    card = CardDefinition(
        name=name,
        mana_cost=None,
        domain="MC",
        text=text,
        characteristics=Characteristics(
            types={CardType.MC_TOOL},
            subtypes={slot.title(), "Gear"},
        ),
    )
    return _attach(
        card,
        mc_cost=cost,
        mc_tool_slot=slot,
        mc_attack=attack,
        mc_armor=armor,
        mc_mining_bonus=mining_bonus,
        mc_keywords=set(mc_keywords) if mc_keywords else None,
    )


def make_action(name: str, cost: dict[str, int], text: str, effect):
    card = CardDefinition(
        name=name,
        mana_cost=None,
        domain="MC",
        text=text,
        characteristics=Characteristics(types={CardType.MC_ACTION}, subtypes={"Action"}),
    )
    return _attach(card, mc_cost=cost, mc_on_play=effect)


# ---------------------------------------------------------------------------
# Effect helpers — used to build interesting on_play / on_block / on_death etc.
# ---------------------------------------------------------------------------

def _opponent(state: GameState, controller: str):
    return next((pid for pid in state.players if pid != controller and not state.players[pid].has_lost), None)


def _gain(materials: dict[str, int]):
    def effect(obj, state, target_id=None):
        return [mc.gain_materials(state, obj.controller, materials)]
    return effect


def _draw(count: int):
    def effect(obj, state, target_id=None):
        return [Event(type=EventType.DRAW, payload={"player": obj.controller, "count": count}, source=obj.id)]
    return effect


def _damage_target(amount: int):
    """Action damage: hit `target_id` if given (already resolved by play_card),
    else hit a frontmost-on-any-column or the avatar."""
    def effect(obj, state, target_id=None):
        target = target_id
        opponent = _opponent(state, obj.controller)
        if not target and opponent:
            for column in range(mc.GRID_SIZE):
                front = mc.column_target(state, opponent, column)
                if front:
                    target = front
                    break
            target = target or opponent
        if not target:
            return []
        return [Event(type=EventType.DAMAGE, payload={"target": target, "amount": amount, "source": obj.id}, source=obj.id)]
    return effect


def _damage_then_destroy_block(amount: int):
    def effect(obj, state, target_id=None):
        events = _damage_target(amount)(obj, state, target_id)
        # If the resolved target is a Block, ALSO destroy it outright.
        if events:
            payload = events[0].payload
            tgt_obj = state.objects.get(payload.get("target"))
            if tgt_obj and CardType.MC_BLOCK in tgt_obj.characteristics.types:
                events.append(Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": tgt_obj.id, "reason": "tnt"}, source=obj.id))
        return events
    return effect


def _summon_token(name: str, attack: int, health: int, subtypes=None, on_death=None):
    def effect(obj, state, target_id=None):
        ev = mc.make_minecraft_token(name, obj.controller, attack, health, set(subtypes or {"Mob"}))
        if on_death:
            ev.payload["token"]["on_death"] = on_death
        return [ev]
    return effect


def _heal_avatar(amount: int):
    def effect(obj, state, target_id=None):
        # Pipeline LIFE_CHANGE handler applies the delta and respects life_cap.
        return [Event(type=EventType.LIFE_CHANGE, payload={"player": obj.controller, "amount": amount}, source=obj.id)]
    return effect


def _untap_workers(count: int):
    def effect(obj, state, target_id=None):
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return []
        events = []
        untapped = 0
        for oid in battlefield.objects:
            if untapped >= count:
                break
            o = state.objects.get(oid)
            if not o or o.controller != obj.controller or CardType.MC_MOB not in o.characteristics.types:
                continue
            if "Worker" not in o.characteristics.subtypes:
                continue
            if o.state.mc_exhausted or o.state.tapped:
                o.state.tapped = False
                o.state.mc_exhausted = False
                untapped += 1
                events.append(Event(type=EventType.UNTAP, payload={"object_id": oid}, source=obj.id))
        # Also reset biome "mined" flags so untapped workers can mine again this turn.
        if untapped:
            for biome in state.minecraft_biomes.get(obj.controller, []):
                biome["mined"] = False
        return events
    return effect


def _explore_any(obj, state, target_id=None):
    biomes = state.minecraft_biomes.get(obj.controller, [])
    for i, biome in enumerate(biomes):
        repl = mc.BIOME_UPGRADES.get(biome.get("name"))
        if repl:
            biomes[i] = dict(repl, yields=dict(repl["yields"]))
            return [Event(type=EventType.MC_EXPLORE_BIOME, payload={"player": obj.controller, "biome_index": i, "biome": biomes[i]}, source=obj.id)]
    return []


def _wither_aoe(obj, state, target_id=None):
    """Wither summons: deal 2 to every opponent grid object."""
    opponent = _opponent(state, obj.controller)
    if not opponent:
        return []
    events = []
    grid = state.minecraft_grid.get(opponent) or []
    for row in grid:
        for oid in row:
            if not oid:
                continue
            events.append(Event(type=EventType.DAMAGE, payload={"target": oid, "amount": 2, "source": obj.id, "is_combat": False}, source=obj.id))
    return events


def _warden_smash(obj, state, target_id=None):
    """Warden enters: deal 4 damage to every enemy mob in the battle row."""
    opponent = _opponent(state, obj.controller)
    if not opponent:
        return []
    events = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return events
    for oid in battlefield.objects:
        o = state.objects.get(oid)
        if not o or o.controller != opponent:
            continue
        if CardType.MC_MOB not in o.characteristics.types:
            continue
        if o.state.mc_grid_x is not None:  # skip on-grid objects
            continue
        events.append(Event(type=EventType.DAMAGE, payload={"target": oid, "amount": 4, "source": obj.id, "is_combat": False}, source=obj.id))
    return events


def _eyes_of_ender(obj, state, target_id=None):
    """Look at top 5 of your library; take an End or Nether Hostile to hand."""
    library = state.zones.get(f"library_{obj.controller}")
    hand = state.zones.get(f"hand_{obj.controller}")
    if not library or not hand or not library.objects:
        return []
    take = None
    for oid in library.objects[:5]:
        o = state.objects.get(oid)
        if not o:
            continue
        st = o.characteristics.subtypes
        if "End" in st or "Nether" in st:
            take = oid
            break
    if not take:
        return []
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": take,
            "from_zone_type": ZoneType.LIBRARY,
            "to_zone_type": ZoneType.HAND,
            "from_zone": f"library_{obj.controller}",
            "to_zone": f"hand_{obj.controller}",
        },
        source=obj.id,
    )]


def _enchant_weapon(obj, state, target_id=None):
    """Enchanting Table on play: permanently +1 attack to your weapon."""
    player = state.players.get(obj.controller)
    if not player:
        return []
    weapon_id = (player.mc_avatar_gear or {}).get("weapon")
    weapon = state.objects.get(weapon_id) if weapon_id else None
    if not weapon or not weapon.card_def:
        return []
    current = int(getattr(weapon.card_def, "mc_attack", 0) or 0)
    setattr(weapon.card_def, "mc_attack", current + 1)
    return []


# ---------- Build-around payoff hooks ----------

def _ender_dragon_etb(obj, state, target_id=None):
    """Ender Dragon: deal 2x diamond-cost permanents you control to opponent."""
    opponent = _opponent(state, obj.controller)
    if not opponent:
        return []
    n = 0
    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in battlefield.objects:
            o = state.objects.get(oid)
            if not o or o.controller != obj.controller or not o.card_def:
                continue
            if oid == obj.id:
                continue
            cost = getattr(o.card_def, "mc_cost", None) or {}
            if int(cost.get("diamond", 0) or 0) > 0:
                n += 1
    if n <= 0:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={"target": opponent, "amount": 2 * n, "source": obj.id, "is_combat": False},
        source=obj.id,
    )]


def _wither_etb(obj, state, target_id=None):
    """Wither: deal damage = 2x hostile count to opponent's avatar."""
    opponent = _opponent(state, obj.controller)
    if not opponent:
        return []
    n = 0
    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in battlefield.objects:
            o = state.objects.get(oid)
            if not o or o.controller != obj.controller:
                continue
            if oid == obj.id:
                continue
            if "Hostile" in o.characteristics.subtypes:
                n += 1
    if n <= 0:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={"target": opponent, "amount": 2 * n, "source": obj.id, "is_combat": False},
        source=obj.id,
    )]


def _iron_golem_etb(obj, state, target_id=None):
    """Iron Golem: deal damage = 2x worker count to opponent's avatar."""
    opponent = _opponent(state, obj.controller)
    if not opponent:
        return []
    n = 0
    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in battlefield.objects:
            o = state.objects.get(oid)
            if not o or o.controller != obj.controller:
                continue
            if "Worker" in o.characteristics.subtypes:
                n += 1
    if n <= 0:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={"target": opponent, "amount": 2 * n, "source": obj.id, "is_combat": False},
        source=obj.id,
    )]


def _elder_guardian_on_event(obj, state, event):
    """Elder Guardian: when a Worker you control mines (any kind of mining
    action), each Worker you control gets +1/+0 until end of turn."""
    if event.type != EventType.MC_MATERIAL_GAIN:
        return []
    payload = event.payload or {}
    if payload.get("player") != obj.controller:
        return []
    # Only react to mining (gain produced by mine_biome) — every mining
    # tick has a non-empty `materials` dict and is keyed to the active
    # player. This avoids triggering on turn-bonus structure ticks (those
    # also use MC_MATERIAL_GAIN, but at turn start we still want pump on
    # incoming Worker mining only when a Worker exists). For balance,
    # gate on "you control at least one Worker on the battlefield."
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    workers = []
    for oid in battlefield.objects:
        o = state.objects.get(oid)
        if not o or o.controller != obj.controller:
            continue
        if "Worker" in o.characteristics.subtypes:
            workers.append(oid)
    if not workers:
        return []
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={"object_id": wid, "power_mod": 1, "toughness_mod": 0, "duration": "end_of_turn"},
        source=obj.id,
    ) for wid in workers]


def _ravager_on_event(obj, state, event):
    """Ravager: when a Block (any) is destroyed, put a +1/+1 counter on Ravager."""
    if event.type != EventType.OBJECT_DESTROYED:
        return []
    target_id = (event.payload or {}).get("object_id")
    target = state.objects.get(target_id) if target_id else None
    if not target or not target.card_def:
        return []
    types = target.card_def.characteristics.types or set()
    if CardType.MC_BLOCK not in types:
        return []
    obj.state.counters["+1/+1"] = obj.state.counters.get("+1/+1", 0) + 1
    return []


def _blaze_on_event(obj, state, event):
    """Blaze: whenever you spend Redstone, Blaze gets +1 ATK until end of turn."""
    if event.type != EventType.MC_MATERIAL_SPEND:
        return []
    payload = event.payload or {}
    if payload.get("player") != obj.controller:
        return []
    materials = payload.get("materials") or {}
    if int(materials.get("redstone", 0) or 0) <= 0:
        return []
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={"object_id": obj.id, "power_mod": 1, "toughness_mod": 0, "duration": "end_of_turn"},
        source=obj.id,
    )]


# ---------- Hook builders for triggered abilities ----------

def _on_block_chip(amount: int):
    def hook(obj, state, attacker_id):
        if not attacker_id:
            return []
        return [Event(type=EventType.DAMAGE, payload={"target": attacker_id, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id)]
    return hook


def _on_block_gain(materials: dict[str, int]):
    def hook(obj, state, attacker_id):
        return [mc.gain_materials(state, obj.controller, materials)]
    return hook


def _on_block_token(name: str, atk: int, hp: int, subtypes=None):
    def hook(obj, state, attacker_id):
        return [mc.make_minecraft_token(name, obj.controller, atk, hp, set(subtypes or {"Mob"}))]
    return hook


def _on_attack_burn(amount: int):
    """When this attacks, also chip the defending player."""
    def hook(obj, state, target_id):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        return [Event(type=EventType.DAMAGE, payload={"target": opp, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id)]
    return hook


def _on_death_column_blast(amount: int):
    """Deal damage to whatever is now frontmost in the column this mob last attacked."""
    def hook(obj, state):
        column = obj.state.mc_last_attack_column
        opp = _opponent(state, obj.controller)
        if column is None or opp is None:
            # Fallback: hit attacker that killed us if we were blocking
            target = obj.state.mc_last_blocked_attacker
            if not target:
                return []
            return [Event(type=EventType.DAMAGE, payload={"target": target, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id)]
        target = mc.column_target(state, opp, int(column)) or opp
        return [Event(type=EventType.DAMAGE, payload={"target": target, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id)]
    return hook


def _on_death_avatar_blast(amount: int):
    """Deal damage to opponent's avatar (TNT Trap going off)."""
    def hook(obj, state):
        opp = _opponent(state, obj.controller)
        if not opp:
            return []
        return [Event(type=EventType.DAMAGE, payload={"target": opp, "amount": amount, "source": obj.id, "is_combat": False}, source=obj.id)]
    return hook


def _on_death_summon(name: str, atk: int, hp: int, subtypes=None):
    def hook(obj, state):
        return [mc.make_minecraft_token(name, obj.controller, atk, hp, set(subtypes or {"Mob"}))]
    return hook


def _wolf_pack_bonus(obj, state):
    """+1 ATK per other Worker you control."""
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
        if CardType.MC_MOB in o.characteristics.types and "Worker" in o.characteristics.subtypes:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Card pool
# ---------------------------------------------------------------------------

_cards = [
    # ===== Workers / passives =====
    make_mob("Steve's Helper", 1, 2, _cost(wood=1), {"Worker"},
             "Worker. Mining yields +1 Wood.",
             mining_bonus={"wood": 1}),
    make_mob("Alex's Scout", 2, 1, _cost(wood=1), {"Worker"},
             "Worker. Haste — can act the turn she's played.",
             mining_bonus="wood", keywords={"haste"}),
    make_mob("Villager Mason", 1, 3, _cost(wood=1, stone=1), {"Villager", "Worker"},
             "Worker. Mining yields +1 Stone.",
             mining_bonus={"stone": 1}),
    make_mob("Allay Courier", 1, 2, _cost(redstone=1), {"Allay", "Worker"},
             "Worker. Mining yields +1 Redstone.",
             mining_bonus={"redstone": 1}),
    make_mob("Panda Forager", 2, 3, _cost(wood=2), {"Animal", "Worker"},
             "Worker. Mining yields +1 Wood.",
             mining_bonus={"wood": 1}),
    make_mob("Wolf Pack", 3, 2, _cost(wood=1, iron=1), {"Animal"},
             "Pack: gains +1 ATK for each other Worker you control.",
             dynamic_attack_bonus=_wolf_pack_bonus),
    make_mob("Snow Golem", 1, 4, _cost(stone=2), {"Golem"},
             "Reach — can block Aerial. When this blocks, deal 1 damage to the attacker.",
             mc_keywords={"reach"},
             on_block=_on_block_chip(1)),
    make_mob("Iron Golem", 3, 4, _cost(iron=1, redstone=1), {"Golem"},
             "When played, deal 2x your Worker count to opponent's avatar. "
             "When destroyed, summon a 0/4 Iron Block.",
             on_play=_iron_golem_etb,
             on_death=_on_death_summon("Iron Block", 0, 4, {"Iron Block", "Mob"})),
    make_mob("Axolotl Guardian", 2, 4, _cost(wood=1, iron=1), {"Animal"},
             "When this blocks, gain 1 Wood.",
             on_block=_on_block_gain({"wood": 1})),
    make_mob("Mooshroom Herd", 2, 5, _cost(wood=2, stone=1), {"Animal"},
             "When played, heal your avatar 2.",
             on_play=_heal_avatar(2)),

    # ===== Hostiles =====
    make_mob("Zombie", 2, 2, _cost(wood=1), {"Hostile", "Undead"},
             "Hostile. +1 ATK at Night."),
    make_mob("Skeleton Archer", 3, 1, _cost(wood=1, stone=1), {"Hostile", "Undead"},
             "Hostile. Ranged + Reach — no counter-damage; can block Aerial.",
             mc_keywords={"ranged", "reach"}),
    make_mob("Creeper", 4, 1, _cost(stone=2), {"Hostile"},
             "Hostile. Deathrattle: deal 3 to the frontmost in the column it attacked.",
             on_death=_on_death_column_blast(3)),
    make_mob("Spider", 2, 3, _cost(wood=1, stone=1), {"Hostile"},
             "Hostile. Climb — ignores Walls.",
             mc_keywords={"climb"}),
    make_mob("Enderman", 4, 4, _cost(iron=2, redstone=1), {"Hostile", "End"},
             "Hostile. When played, draw a card.",
             on_play=_draw(1)),
    make_mob("Blaze", 3, 3, _cost(redstone=2, iron=1), {"Hostile", "Nether"},
             "Hostile. Ranged. When this attacks, deal 1 to the defender's avatar. "
             "Whenever you spend Redstone, Blaze gets +1 ATK until end of turn.",
             mc_keywords={"ranged"},
             on_attack=_on_attack_burn(1),
             on_event=_blaze_on_event),
    make_mob("Ghast", 5, 3, _cost(redstone=2, diamond=1), {"Hostile", "Nether"},
             "Hostile. Aerial — ignores Blocks.",
             mc_keywords={"aerial"}),
    make_mob("Piglin Raider", 3, 2, _cost(iron=1, redstone=1), {"Hostile", "Nether", "Raider"},
             "Hostile. Raider tempo body."),
    make_mob("Pillager Patrol", 3, 3, _cost(wood=1, iron=2), {"Hostile", "Raider"},
             "Other Raiders you control gain +1 ATK.",
             lord_bonus={"subtypes": {"Raider"}, "attack": 1}),
    make_mob("Ravager", 4, 3, _cost(iron=1, redstone=1), {"Hostile", "Raider"},
             "Siege — destroys frontmost Block in attacked column. "
             "Whenever a Block is destroyed, put a +1/+1 counter on Ravager.",
             mc_keywords={"siege"},
             on_event=_ravager_on_event),

    # ===== Bosses / iconic high-end =====
    make_mob("Warden", 7, 8, _cost(iron=4, redstone=2, diamond=1), {"Hostile", "Boss"},
             "When played, deal 4 damage to every enemy mob in the battle row.",
             on_play=_warden_smash),
    make_mob("Elder Guardian", 4, 6, _cost(stone=2, iron=1), {"Hostile", "Boss"},
             "Boss. Whenever a Worker you control mines, each Worker you control gets +1 ATK until end of turn.",
             on_event=_elder_guardian_on_event),
    make_mob("Wither", 4, 4, _cost(redstone=1, iron=1), {"Hostile", "Boss", "Nether"},
             "When played, deal 2x your Hostile count to opponent's avatar.",
             on_play=_wither_etb),
    make_mob("Ender Dragon", 6, 6, _cost(iron=1, diamond=2), {"Hostile", "Boss", "End"},
             "Aerial. When played, deal 2 damage to opponent for each other Diamond-cost permanent you control.",
             mc_keywords={"aerial"},
             on_play=_ender_dragon_etb),
    make_mob("Shulker Sentry", 3, 5, _cost(redstone=2, diamond=1), {"Hostile", "End"},
             "When this blocks, summon a 0/2 Shulker Bullet.",
             on_block=_on_block_token("Shulker Bullet", 0, 2, {"Mob", "End"})),

    # ===== Structures =====
    make_structure("Bed", 4, _cost(wood=2), {"Structure", "Bed"},
                   "If your Avatar dies while you control a Bed, respawn at 20 and discard gear."),
    make_structure("Crafting Table", 3, _cost(wood=1), {"Structure", "Crafting"},
                   "Start of turn: gain 1 Wood.",
                   turn_bonus={"wood": 1}),
    make_structure("Furnace", 5, _cost(stone=2), {"Structure", "Furnace"},
                   "Start of turn: gain 1 Iron.",
                   turn_bonus={"iron": 1}),
    make_structure("Chest", 3, _cost(wood=2), {"Structure", "Storage"},
                   "Start of turn: draw a card.",
                   turn_draw=1),
    make_structure("Farm Plot", 4, _cost(wood=1, stone=1), {"Structure", "Farm"},
                   "Start of turn: gain 1 Wood. When played: heal 2.",
                   turn_bonus={"wood": 1},
                   on_play=_heal_avatar(2)),
    make_structure("Redstone Engine", 4, _cost(stone=1, redstone=2), {"Structure", "Redstone"},
                   "Start of turn: gain 1 Redstone.",
                   turn_bonus={"redstone": 1}),
    make_structure("Enchanting Table", 5, _cost(stone=2, diamond=1), {"Structure", "Enchanting"},
                   "Start of turn: gain 1 Diamond. When played: your equipped weapon gets +1 ATK.",
                   turn_bonus={"diamond": 1},
                   on_play=_enchant_weapon),
    make_structure("Nether Portal", 6, _cost(stone=3, redstone=2), {"Structure", "Nether"},
                   "Start of turn: gain 1 Redstone.",
                   turn_bonus={"redstone": 1}),
    make_structure("End Portal Frame", 7, _cost(stone=3, diamond=2), {"Structure", "End"},
                   "Start of turn: gain 1 Diamond.",
                   turn_bonus={"diamond": 1}),
    make_structure("Beacon", 7, _cost(iron=2, diamond=2, redstone=1), {"Structure", "Beacon"},
                   "Start of turn: gain 1 Iron and 1 Redstone. Your Workers get +1 ATK.",
                   turn_bonus={"iron": 1, "redstone": 1},
                   lord_bonus={"subtypes": {"Worker"}, "attack": 1}),
    make_structure("Village Watchtower", 5, _cost(wood=2, stone=2), {"Structure", "Village"},
                   "Your Villagers get +1 ATK.",
                   lord_bonus={"subtypes": {"Villager"}, "attack": 1}),

    # ===== Blocks (column shields) =====
    make_structure("Cobblestone Wall", 6, _cost(stone=2), {"Block", "Wall"},
                   "Wall — soaks damage in its column.",
                   is_block=True),
    make_structure("Oak Planks", 3, _cost(wood=1), {"Block", "Wall"},
                   "Cheap wall.",
                   is_block=True),
    make_structure("Iron Door", 5, _cost(iron=2), {"Block", "Door"},
                   "Durable door.",
                   is_block=True),
    make_structure("Obsidian Block", 9, _cost(stone=3, diamond=1), {"Block", "Wall"},
                   "Premium wall.",
                   is_block=True),
    make_structure("TNT Trap", 2, _cost(redstone=1, stone=1), {"Block", "Trap"},
                   "Deathrattle: deal 4 damage to opponent's avatar.",
                   is_block=True,
                   on_death=_on_death_avatar_blast(4)),
    make_structure("Redstone Lamp", 3, _cost(redstone=1, stone=1), {"Block", "Redstone"},
                   "Start of turn: gain 1 Redstone.",
                   is_block=True,
                   turn_bonus={"redstone": 1}),
    make_structure("Water Bucket Moat", 4, _cost(iron=1, stone=1), {"Block", "Moat"},
                   "Wall variant.",
                   is_block=True),
    make_structure("Piston Gate", 5, _cost(redstone=2, iron=1), {"Block", "Redstone"},
                   "Wall variant.",
                   is_block=True),

    # ===== Tools =====
    make_tool("Wooden Pickaxe", "tool", _cost(wood=1),
              "Avatar mines +1 Stone.",
              mining_bonus={"stone": 1}),
    make_tool("Iron Pickaxe", "tool", _cost(wood=1, iron=2),
              "Avatar mines +1 Iron.",
              mining_bonus={"iron": 1}),
    make_tool("Diamond Pickaxe", "tool", _cost(wood=1, diamond=2),
              "Avatar mines +1 Diamond.",
              mining_bonus={"diamond": 1}),
    make_tool("Iron Sword", "weapon", _cost(iron=2),
              "Avatar attack deals 4.",
              attack=4),
    make_tool("Diamond Sword", "weapon", _cost(diamond=2, iron=1),
              "Avatar attack deals 6.",
              attack=6),
    make_tool("Bow", "weapon", _cost(wood=2, iron=1),
              "Avatar attack deals 3. Ranged.",
              attack=3, mc_keywords={"ranged"}),
    make_tool("Crossbow", "weapon", _cost(wood=1, iron=2, redstone=1),
              "Avatar attack deals 5. Ranged.",
              attack=5, mc_keywords={"ranged"}),
    make_tool("Iron Armor", "armor", _cost(iron=3),
              "Avatar takes 2 less damage.",
              armor=2),
    make_tool("Diamond Armor", "armor", _cost(diamond=3, iron=1),
              "Avatar takes 4 less damage.",
              armor=4),
    make_tool("Netherite Armor", "armor", _cost(diamond=3, redstone=2, iron=2),
              "Avatar takes 5 less damage.",
              armor=5),
    make_tool("Elytra", "armor", _cost(diamond=2, redstone=2),
              "Avatar takes 1 less damage. Aerial.",
              armor=1, mc_keywords={"aerial"}),

    # ===== Actions =====
    make_action("Chop Trees", _cost(), "Gain 2 Wood.", _gain({"wood": 2})),
    make_action("Strip Mine", _cost(stone=1), "Gain 1 Iron and 1 Redstone.",
                _gain({"iron": 1, "redstone": 1})),
    make_action("Find Diamonds", _cost(iron=2), "Gain 1 Diamond.", _gain({"diamond": 1})),
    make_action("Villager Trade", _cost(wood=1), "Draw a card.", _draw(1)),
    make_action("Bone Meal", _cost(wood=1),
                "Untap a Worker; that Worker can mine again this turn.",
                _untap_workers(1)),
    make_action("TNT Blast", _cost(redstone=1, stone=1),
                "Deal 4 to a target. If it's a Block, also destroy it.",
                _damage_then_destroy_block(4)),
    make_action("Creeper Ambush", _cost(stone=2),
                "Summon a 4/1 Creeper token (deathrattle: deal 3 to its column).",
                _summon_token("Creeper", 4, 1, {"Hostile", "Mob"})),
    make_action("Redstone Contraption", _cost(redstone=2),
                "Untap up to 2 Workers.",
                _untap_workers(2)),
    make_action("Explore Map", _cost(wood=1), "Upgrade a biome.", _explore_any),
    make_action("Village Reinforcements", _cost(wood=2, iron=1),
                "Create a 2/3 Village Guard.",
                _summon_token("Village Guard", 2, 3, {"Mob", "Villager"})),
    make_action("Nether Expedition", _cost(redstone=1, iron=1),
                "Gain 1 Redstone and draw a card.",
                lambda obj, state, target_id=None: [
                    mc.gain_materials(state, obj.controller, {"redstone": 1}),
                    Event(type=EventType.DRAW, payload={"player": obj.controller, "count": 1}, source=obj.id),
                ]),
    make_action("Eyes of Ender", _cost(redstone=1, diamond=1),
                "Search top 5 of your deck; take an End or Nether mob to hand.",
                _eyes_of_ender),
    make_action("Totem of Undying", _cost(diamond=1, redstone=2),
                "Heal your avatar to 20.",
                _heal_avatar(20)),
]


MINECRAFT_CARDS = {card.name: card for card in _cards}


# ---------------------------------------------------------------------------
# Starter decks
# ---------------------------------------------------------------------------

BUILDER_NAMES = [
    "Bed", "Crafting Table", "Furnace", "Chest", "Farm Plot",
    "Redstone Engine", "Village Watchtower", "Cobblestone Wall", "Oak Planks", "Iron Door",
    "Water Bucket Moat", "Piston Gate", "Steve's Helper", "Alex's Scout", "Villager Mason",
    "Panda Forager", "Wolf Pack", "Snow Golem", "Iron Golem", "Allay Courier",
    "Bow", "Iron Sword", "Iron Armor", "Chop Trees", "Village Reinforcements",
]

MINER_NAMES = [
    "Bed", "Crafting Table", "Furnace", "Chest", "Enchanting Table",
    "Nether Portal", "End Portal Frame", "Beacon", "Steve's Helper", "Alex's Scout",
    "Villager Mason", "Allay Courier", "Panda Forager", "Shulker Sentry", "Elder Guardian",
    "Warden", "Ender Dragon", "Wooden Pickaxe", "Iron Pickaxe", "Diamond Pickaxe",
    "Diamond Armor", "Chop Trees", "Strip Mine", "Find Diamonds", "Explore Map",
]

RAIDER_NAMES = [
    "Bed", "Oak Planks", "TNT Trap", "Zombie", "Skeleton Archer",
    "Creeper", "Spider", "Piglin Raider", "Pillager Patrol", "Ravager",
    "Enderman", "Blaze", "Wolf Pack", "Steve's Helper", "Alex's Scout",
    "Iron Sword", "Diamond Sword", "Bow", "Crossbow", "Chop Trees",
    "Strip Mine", "TNT Blast", "Creeper Ambush", "Nether Expedition", "Wither",
]


def _deck(names: list[str]) -> list[CardDefinition]:
    return [MINECRAFT_CARDS[name] for name in names for _ in range(2)]


def make_builder_deck() -> list[CardDefinition]:
    return _deck(BUILDER_NAMES)


def make_miner_deck() -> list[CardDefinition]:
    return _deck(MINER_NAMES)


def make_raider_deck() -> list[CardDefinition]:
    return _deck(RAIDER_NAMES)


MINECRAFT_STARTER_DECKS = {
    "builder": make_builder_deck,
    "miner": make_miner_deck,
    "raider": make_raider_deck,
}
