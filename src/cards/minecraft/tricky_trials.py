"""Tricky Trials - Minecraft TCG expansion (MCT).

Expansion code: MCT

Design/cost notes:
  - Costing follows the Minecraft calibration implicit in alpha: a 1-material
    mob is about 2/2, 2 materials is about 3/3 or a keyworded 2/3, draw 1 is
    worth roughly 1-2 mixed materials, and recurring material production is
    priced as a fragile 3-5 durability structure.
  - Spice cards are intentionally pushed by about one material when they need
    a real board context: Trial needs structures/blocks, Tame needs Animals,
    Pulse needs redstone spend, Echo needs deaths, Raid needs attack pressure,
    and Voyage needs End/diamond support.

Supported mechanics in this module:
  - Trial: bonus if you control a Trial/Chamber permanent or several grid
    permanents. Implemented with on_play checks and lords.
  - Tame: Animal/Friend package with Pack bonuses, healing, and Worker support.
  - Pulse: redstone-spend reactions through mc_on_event(MC_MATERIAL_SPEND).
  - Echo: death reactions through mc_on_event(OBJECT_DESTROYED/EXILE).
  - Raid: Hostile/Raider attack and night payoffs.
  - Voyage: End/Aerial/diamond-ramp cards that reward premium resources.

All mechanics are approximations that the current simulator can execute.
There are no hidden choices: when a tabletop version would choose a mode or
target, these cards use deterministic targets so AI-vs-AI games remain stable.
"""

from __future__ import annotations

from src.engine.types import CardDefinition, CardType, Event, EventType, GameState, ZoneType
from src.engine import minecraft as mc
from src.engine.queries import get_toughness
from .alpha import make_mob, make_structure, make_tool, make_action, _attach, _cost


SET_CODE = "MCT"


def _tag(card: CardDefinition, *mechanics: str) -> CardDefinition:
    existing = set(getattr(card, "mc_mechanics", set()) or set())
    existing.update(mechanics)
    return _attach(card, mc_set_code=SET_CODE, mc_mechanics=existing)


def _opponent(state: GameState, controller: str) -> str | None:
    return next((pid for pid in state.players if pid != controller and not state.players[pid].has_lost), None)


def _controlled(
    state: GameState,
    controller: str,
    *,
    subtype: str | None = None,
    card_type: CardType | None = None,
):
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    out = []
    for oid in list(battlefield.objects):
        obj = state.objects.get(oid)
        if not obj or obj.controller != controller or obj.zone != ZoneType.BATTLEFIELD:
            continue
        if subtype and subtype not in obj.characteristics.subtypes:
            continue
        if card_type and card_type not in obj.characteristics.types:
            continue
        out.append(obj)
    return out


def _controlled_count(state: GameState, controller: str, subtype: str | None = None) -> int:
    return len(_controlled(state, controller, subtype=subtype))


def _grid_count(state: GameState, controller: str) -> int:
    count = 0
    for row in state.minecraft_grid.get(controller, []) or []:
        for oid in row:
            obj = state.objects.get(oid) if oid else None
            if obj and obj.controller == controller and obj.zone == ZoneType.BATTLEFIELD:
                count += 1
    return count


def _has_trial(state: GameState, controller: str) -> bool:
    return bool(
        _controlled(state, controller, subtype="Trial")
        or _controlled(state, controller, subtype="Chamber")
        or _grid_count(state, controller) >= 2
    )


def _gain(materials: dict[str, int]):
    def effect(obj, state, target_id=None):
        return [mc.gain_materials(state, obj.controller, materials)]
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


def _damage_resolve(obj, state, target_id: str | None, amount: int) -> list[Event]:
    """Deterministic damage resolver. Returns the DAMAGE event for the chosen
    target. Empty list if no valid target."""
    if not target_id:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={"target": target_id, "amount": amount, "source": obj.id, "is_combat": False},
        source=obj.id,
    )]


def _damage_target(amount: int):
    """MCT damage helper. Phase 4 PendingChoice demo for Minecraft.

    If a target_id is pre-resolved by ``play_card`` (i.e. the controller
    chose a column on the frontend), apply damage directly. Otherwise emit
    a ``PendingChoice`` over the opponent's frontmost-per-column mobs plus
    the avatar fallback. AI behavior is preserved via ``heuristic_pick``,
    which matches the old auto-pick (first-found frontmost mob across
    columns; else the avatar). Humans now get a real target choice.
    """
    def effect(obj, state, target_id=None):
        if target_id:
            return _damage_resolve(obj, state, target_id, amount)

        opp = _opponent(state, obj.controller)
        if not opp:
            return []

        # Gather frontmost-per-column mobs (the original auto-pick set) and
        # the avatar fallback. This is the demo's option universe.
        frontmost_ids: list[str] = []
        for column in range(mc.GRID_SIZE):
            front = mc.column_target(state, opp, column)
            if front and front not in frontmost_ids:
                frontmost_ids.append(front)

        # Short-circuit: no mobs and no opponent avatar → no-op. (opp truthy
        # means at minimum the avatar is a valid target, so this branch is
        # rarely hit.)
        if not frontmost_ids and not opp:
            return []

        # Old auto-pick: first-found frontmost mob across columns, else avatar.
        auto_pick = frontmost_ids[0] if frontmost_ids else opp

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        def _option_for_mob(mob_id: str) -> dict:
            mob = state.objects.get(mob_id)
            name = getattr(getattr(mob, "card_def", None), "name", mob_id) if mob else mob_id
            power = getattr(getattr(mob, "characteristics", None), "power", None) if mob else None
            toughness = getattr(getattr(mob, "characteristics", None), "toughness", None) if mob else None
            if power is not None and toughness is not None:
                description = f"Mob {power}/{toughness}"
            else:
                description = "Mob"
            return {"id": mob_id, "label": str(name), "description": description}

        opp_player = state.players.get(opp)
        opp_label = getattr(opp_player, "name", opp) if opp_player else opp
        avatar_life = getattr(opp_player, "life", None) if opp_player else None
        avatar_desc = f"Avatar · {avatar_life} life" if avatar_life is not None else "Avatar"

        options = [_option_for_mob(mid) for mid in frontmost_ids]
        options.append({"id": opp, "label": f"{opp_label} (Avatar)", "description": avatar_desc})

        def _resolve_handler(choice, selected, st):
            chosen = selected[0] if selected else auto_pick
            if isinstance(chosen, dict):
                chosen = chosen.get("id", auto_pick)
            return _damage_resolve(obj, st, chosen, amount)

        return create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=obj.controller,
            prompt=f"Deal {amount} damage to which target?",
            options=options,
            source_id=obj.id,
            min_choices=1,
            max_choices=1,
            handler=_resolve_handler,
            heuristic_pick=[auto_pick],
        )
    return effect


def _destroy_target(kind: str | None = None):
    def effect(obj, state, target_id=None):
        target = state.objects.get(target_id) if target_id else None
        if not target:
            return []
        if kind == "mob" and CardType.MC_MOB not in target.characteristics.types:
            return []
        if kind == "block" and CardType.MC_BLOCK not in target.characteristics.types:
            return []
        return [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={"object_id": target.id, "reason": "mct_destroy"},
            source=obj.id,
        )]
    return effect


def _summon_token(name: str, attack: int, health: int, subtypes: set[str]):
    def effect(obj, state, target_id=None):
        return [mc.make_minecraft_token(name, obj.controller, attack, health, set(subtypes) | {"Mob"})]
    return effect


def _on_death_summon(name: str, attack: int, health: int, subtypes: set[str], count: int = 1):
    def effect(obj, state):
        return [
            mc.make_minecraft_token(name, obj.controller, attack, health, set(subtypes) | {"Mob"})
            for _ in range(count)
        ]
    return effect


def _trial_reward(materials: dict[str, int] | None = None, draw: int = 0, damage: int = 0):
    def effect(obj, state, target_id=None):
        events: list[Event] = []
        if materials:
            events.append(mc.gain_materials(state, obj.controller, materials))
        if _has_trial(state, obj.controller):
            if draw:
                events.append(Event(type=EventType.DRAW, payload={"player": obj.controller, "count": draw}, source=obj.id))
            if damage:
                events.extend(_damage_target(damage)(obj, state, target_id))
        return events
    return effect


def _trial_scale_bonus(obj, state) -> int:
    return min(4, _grid_count(state, obj.controller) // 2)


def _pack_bonus(obj, state) -> int:
    friend_ids = {
        other.id
        for other in _controlled(state, obj.controller)
        if "Animal" in other.characteristics.subtypes or "Friend" in other.characteristics.subtypes
    }
    return max(0, len(friend_ids) - 1)


def _end_bonus(obj, state) -> int:
    end_count = _controlled_count(state, obj.controller, "End")
    diamonds = int((state.players.get(obj.controller).mc_materials or {}).get("diamond", 0) or 0)
    return min(5, max(0, end_count - 1) + min(2, diamonds))


def _raid_bonus(obj, state) -> int:
    base = _controlled_count(state, obj.controller, "Raider") // 2
    return base + (1 if state.minecraft_day_phase == "night" else 0)


def _echo_gain(materials: dict[str, int] | None = None, draw: int = 0, token: tuple[str, int, int, set[str]] | None = None):
    def hook(obj, state, event):
        if event.type not in {EventType.OBJECT_DESTROYED, EventType.EXILE}:
            return []
        target_id = event.payload.get("object_id")
        dead = state.objects.get(target_id) if target_id else None
        if not dead or CardType.MC_MOB not in dead.characteristics.types:
            return []
        events: list[Event] = []
        if materials:
            events.append(mc.gain_materials(state, obj.controller, materials))
        if draw:
            events.append(Event(type=EventType.DRAW, payload={"player": obj.controller, "count": draw}, source=obj.id))
        if token:
            name, attack, health, subtypes = token
            events.append(mc.make_minecraft_token(name, obj.controller, attack, health, set(subtypes) | {"Mob"}))
        return events
    return hook


def _pulse(
    *,
    gain: dict[str, int] | None = None,
    draw: int = 0,
    damage: int = 0,
    token: tuple[str, int, int, set[str]] | None = None,
):
    def hook(obj, state, event):
        if event.type != EventType.MC_MATERIAL_SPEND:
            return []
        payload = event.payload or {}
        if payload.get("player") != obj.controller:
            return []
        spent = payload.get("materials") or {}
        if int(spent.get("redstone", 0) or 0) <= 0:
            return []
        events: list[Event] = []
        if gain:
            events.append(mc.gain_materials(state, obj.controller, gain))
        if draw:
            events.append(Event(type=EventType.DRAW, payload={"player": obj.controller, "count": draw}, source=obj.id))
        if damage:
            opp = _opponent(state, obj.controller)
            if opp:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={"target": opp, "amount": damage, "source": obj.id, "is_combat": False},
                    source=obj.id,
                ))
        if token:
            name, attack, health, subtypes = token
            events.append(mc.make_minecraft_token(name, obj.controller, attack, health, set(subtypes) | {"Mob"}))
        return events
    return hook


def _on_attack_gain(materials: dict[str, int]):
    def effect(obj, state, target_id=None):
        return [mc.gain_materials(state, obj.controller, materials)]
    return effect


def _on_attack_if_raid(damage: int):
    def effect(obj, state, target_id=None):
        if state.minecraft_day_phase != "night" and _controlled_count(state, obj.controller, "Raider") < 2:
            return []
        return _damage_avatar(damage)(obj, state, target_id)
    return effect


def _wounded_destroy(threshold: int):
    def effect(obj, state, target_id=None):
        target = state.objects.get(target_id) if target_id else None
        if not target or CardType.MC_MOB not in target.characteristics.types:
            return []
        remaining = max(0, int(get_toughness(target, state) or 0) - int(target.state.damage or 0))
        if remaining > threshold:
            return []
        return [Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": target.id, "reason": "mct_wounded"}, source=obj.id)]
    return effect


def _explore_any(obj, state, target_id=None):
    player = state.players.get(obj.controller)
    if not player or player.mc_avatar_action_used:
        return []
    for i, biome in enumerate(state.minecraft_biomes.get(obj.controller, []) or []):
        if mc.BIOME_UPGRADES.get(biome.get("name")):
            ok, _msg, events = mc.explore_biome(state._game, obj.controller, i)
            return events if ok else []
    return []


def _two_effects(*effects):
    def effect(obj, state, target_id=None):
        events: list[Event] = []
        for fn in effects:
            events.extend(fn(obj, state, target_id) or [])
        return events
    return effect


_cards: list[CardDefinition] = []


def _add(card: CardDefinition, *mechanics: str) -> CardDefinition:
    card = _tag(card, *mechanics)
    _cards.append(card)
    return card


# ---------------------------------------------------------------------------
# Shared economy and defensive commons
# ---------------------------------------------------------------------------

for name, cost, bonus, durability, text in [
    ("Cherry Grove", _cost(wood=1), {"wood": 1}, 3, "Start of turn: gain 1 Wood."),
    ("Bamboo Workshop", _cost(wood=1, stone=1), {"wood": 1}, 4, "Start of turn: gain 1 Wood."),
    ("Copper Mine", _cost(stone=1), {"iron": 1}, 3, "Start of turn: gain 1 Iron."),
    ("Tuff Quarry", _cost(stone=2), {"stone": 1}, 5, "Start of turn: gain 1 Stone."),
    ("Amethyst Vein", _cost(stone=1, redstone=1), {"redstone": 1}, 4, "Start of turn: gain 1 Redstone."),
    ("Ancient Dig Site", _cost(stone=1, iron=1), {"stone": 1, "iron": 1}, 5, "Start of turn: gain Stone and Iron."),
    ("Deep Ore Vein", _cost(stone=2, iron=1), {"redstone": 1}, 5, "Start of turn: gain 1 Redstone."),
    ("Geode Observatory", _cost(wood=1, redstone=1), {"redstone": 1}, 4, "Start of turn: gain 1 Redstone."),
    ("Trial Supply Cache", _cost(wood=1, stone=1), {}, 3, "Start of turn: draw a card."),
    ("Map Room", _cost(wood=2), {}, 3, "Start of turn: draw a card."),
    ("Village Granary", _cost(wood=1), {"wood": 1}, 4, "Start of turn: gain 1 Wood."),
    ("Ore Smeltery", _cost(stone=2, iron=1), {"iron": 1}, 5, "Start of turn: gain 1 Iron."),
]:
    _add(make_structure(
        name,
        durability,
        cost,
        {"Structure", "Economy"},
        text,
        turn_bonus=bonus,
        turn_draw=1 if name in {"Trial Supply Cache", "Map Room"} else 0,
    ), "Economy")

for name, cost, durability, subtypes in [
    ("Mud Brick Wall", _cost(stone=1), 4, {"Block", "Wall"}),
    ("Deepslate Bulwark", _cost(stone=2), 7, {"Block", "Wall"}),
    ("Copper Grate", _cost(iron=1), 4, {"Block", "Copper"}),
    ("Waxed Copper Door", _cost(iron=1, redstone=1), 6, {"Block", "Copper", "Door"}),
    ("Trial Barrier", _cost(stone=1, redstone=1), 5, {"Block", "Trial", "Chamber"}),
    ("Sculk Veil", _cost(stone=1, redstone=1), 3, {"Block", "Sculk"}),
    ("Bastion Barricade", _cost(stone=1, iron=1), 5, {"Block", "Raid"}),
    ("End Stone Shield", _cost(stone=1, diamond=1), 6, {"Block", "End"}),
]:
    _add(make_structure(name, durability, cost, subtypes, "Block. Protects its column.", is_block=True), "Defense")

for name, cost, effect, text in [
    ("Punch Trees", _cost(), _gain({"wood": 2}), "Gain 2 Wood."),
    ("Mine Tuff", _cost(stone=1), _gain({"stone": 2}), "Gain 2 Stone."),
    ("Smelt Copper", _cost(stone=1), _gain({"iron": 1, "redstone": 1}), "Gain Iron and Redstone."),
    ("Scout New Biome", _cost(wood=1), _explore_any, "Upgrade your first available biome."),
    ("Bundle Up", _cost(wood=1), _draw(1), "Draw a card."),
    ("Trail Rations", _cost(wood=1), _heal(5), "Heal 5."),
    ("Suspicious Gravel", _cost(stone=1), _two_effects(_gain({"redstone": 1}), _draw(1)), "Gain Redstone and draw."),
    ("Ancient Debris Map", _cost(iron=1, redstone=1), _gain({"diamond": 1}), "Gain a Diamond."),
    ("Breeze Charge", _cost(redstone=1), _damage_target(2), "Deal 2 to a target."),
    ("Wind Burst", _cost(wood=1, redstone=1), _damage_target(3), "Deal 3 to a target."),
    ("Vault Key", _cost(redstone=1), _two_effects(_gain({"iron": 1}), _draw(1)), "Gain Iron and draw."),
    ("Crafting Sprint", _cost(wood=1), _gain({"wood": 1, "stone": 1}), "Gain Wood and Stone."),
]:
    _add(make_action(name, cost, text, effect), "Economy")

for name, atk, hp, cost, bonus in [
    ("Trail Mapper", 1, 3, _cost(wood=1), {"stone": 1}),
    ("Copper Miner", 1, 2, _cost(wood=1), {"iron": 1}),
    ("Bamboo Farmer", 1, 3, _cost(wood=1), {"wood": 1}),
    ("Geode Prospector", 1, 2, _cost(wood=1, stone=1), {"redstone": 1}),
    ("Ancient Miner", 2, 3, _cost(wood=1, iron=1), {"stone": 1, "iron": 1}),
    ("Deep Delver", 2, 2, _cost(wood=1, redstone=1), {"redstone": 1}),
]:
    _add(make_mob(name, atk, hp, cost, {"Worker", "Villager"}, f"Worker. Mines with bonus {bonus}.", mining_bonus=bonus), "Economy")


# ---------------------------------------------------------------------------
# Trial Chambers
# ---------------------------------------------------------------------------

for name, cost, durability, bonus in [
    ("Trial Spawner", _cost(stone=1, redstone=1), 4, {"stone": 1}),
    ("Ominous Trial Spawner", _cost(stone=1, iron=1, redstone=1), 5, {"redstone": 1}),
    ("Vault of Rewards", _cost(wood=1, redstone=1), 4, {}),
    ("Chamber Hallway", _cost(stone=1), 4, {"stone": 1}),
    ("Breeze Cage", _cost(stone=1, redstone=1), 4, {"redstone": 1}),
    ("Trial Armory", _cost(wood=1, iron=1), 4, {"iron": 1}),
    ("Copper Trial Gate", _cost(iron=1, redstone=1), 5, {"iron": 1}),
    ("Wind Tunnel", _cost(wood=1, redstone=1), 3, {}),
]:
    _add(make_structure(
        name,
        durability,
        cost,
        {"Structure", "Trial", "Chamber"},
        "Trial. Start of turn: material reward." if bonus else "Trial. Start of turn: draw a card.",
        turn_bonus=bonus,
        turn_draw=0 if bonus else 1,
    ), "Trial")

for name, atk, hp, cost, kws, play in [
    ("Breeze", 3, 2, _cost(wood=1, redstone=1), {"ranged"}, _trial_reward({"redstone": 1}, damage=2)),
    ("Bogged Archer", 2, 2, _cost(wood=1, stone=1), {"ranged", "reach"}, _trial_reward(draw=1)),
    ("Trial Skeleton", 3, 2, _cost(wood=1, stone=1), {"ranged"}, None),
    ("Trial Zombie", 3, 3, _cost(wood=1, stone=1), set(), None),
    ("Vault Sentinel", 2, 5, _cost(stone=1, iron=1), {"reach"}, _trial_reward({"iron": 1})),
    ("Chamber Slime", 2, 3, _cost(stone=1), set(), None),
    ("Breeze Caller", 2, 4, _cost(wood=1, redstone=1), set(), _summon_token("Breeze Wisp", 1, 1, {"Trial"})),
    ("Ominous Captain", 4, 4, _cost(iron=1, redstone=1), set(), _trial_reward(draw=1, damage=2)),
    ("Vault Golem", 4, 6, _cost(iron=2, redstone=1), {"reach"}, _trial_reward({"diamond": 1})),
    ("Chamber Champion", 5, 5, _cost(stone=1), set(), _trial_reward(draw=1, damage=3)),
]:
    _add(make_mob(name, atk, hp, cost, {"Hostile", "Trial"}, "Trial payoff.", mc_keywords=kws, on_play=play), "Trial")

for name, atk, hp, cost in [
    ("Trial Duelist", 2, 3, _cost(wood=1, stone=1)),
    ("Vault Breaker", 3, 3, _cost(stone=1, iron=1)),
    ("Hallway Ambusher", 4, 2, _cost(wood=1, iron=1)),
    ("Chamber Guardian", 3, 5, _cost(stone=2, iron=1)),
    ("Trial Ravager", 5, 4, _cost(iron=1, redstone=1)),
]:
    _add(make_mob(
        name,
        atk,
        hp,
        cost,
        {"Hostile", "Trial"},
        "Trial: gets stronger as your grid fills.",
        dynamic_attack_bonus=_trial_scale_bonus,
    ), "Trial")

for name, cost, effect, text in [
    ("Open the Vault", _cost(redstone=1), _trial_reward({"iron": 1}, draw=1), "Gain Iron. Trial: draw."),
    ("Ominous Bottle", _cost(wood=1), _trial_reward({"redstone": 1}, damage=2), "Gain Redstone. Trial: deal 2."),
    ("Trial Cleave", _cost(stone=1, redstone=1), _damage_target(4), "Deal 4 to a target."),
    ("Spawn Wave", _cost(wood=1, stone=1), _summon_token("Trial Zombie", 3, 3, {"Hostile", "Trial"}), "Summon a Trial Zombie."),
    ("Breeze Knockback", _cost(redstone=1), _damage_target(2), "Deal 2 to a target."),
    ("Chamber Rewards", _cost(iron=1), _trial_reward({"wood": 1, "stone": 1}, draw=2), "Gain Wood and Stone. Trial: draw 2."),
    ("Vault Jackpot", _cost(iron=1, redstone=1), _trial_reward({"diamond": 1}, draw=1), "Gain Diamond. Trial: draw."),
    ("Ominous Trial", _cost(redstone=2), _two_effects(_summon_token("Breeze", 3, 2, {"Hostile", "Trial"}), _draw(1)), "Summon a Breeze and draw."),
]:
    _add(make_action(name, cost, text, effect), "Trial")


# ---------------------------------------------------------------------------
# Tame and Animal friends
# ---------------------------------------------------------------------------

for name, atk, hp, cost, subtypes, play, block in [
    ("Armadillo Friend", 1, 4, _cost(wood=1), {"Animal", "Friend"}, _heal(2), None),
    ("Wolf Companion", 3, 2, _cost(wood=1, stone=1), {"Animal", "Friend"}, None, None),
    ("Cat Familiar", 1, 2, _cost(wood=1), {"Animal", "Friend"}, _draw(1), None),
    ("Camel Caravan", 2, 5, _cost(wood=2, stone=1), {"Animal", "Friend"}, _gain({"wood": 1}), None),
    ("Sniffer Calf", 1, 3, _cost(wood=1), {"Animal", "Friend"}, _gain({"wood": 1}), None),
    ("Frog Choir", 2, 3, _cost(wood=1, stone=1), {"Animal", "Friend"}, _heal(3), None),
    ("Fox Courier", 2, 2, _cost(wood=1), {"Animal", "Friend"}, _draw(1), None),
    ("Llama Trader", 2, 4, _cost(wood=1, iron=1), {"Animal", "Friend", "Villager"}, _gain({"iron": 1}), None),
    ("Parrot Scout", 2, 1, _cost(wood=1), {"Animal", "Friend"}, None, None),
    ("Bee Swarm", 1, 1, _cost(wood=1), {"Animal", "Friend"}, _summon_token("Bee", 1, 1, {"Animal", "Friend"}), None),
    ("Panda Protector", 2, 6, _cost(wood=2, stone=1), {"Animal", "Friend"}, None, _heal(2)),
    ("Glow Squid Guide", 1, 3, _cost(wood=1, redstone=1), {"Animal", "Friend"}, _gain({"redstone": 1}), None),
]:
    kws = {"aerial"} if name == "Parrot Scout" else set()
    _add(make_mob(name, atk, hp, cost, subtypes, "Tame support.", mc_keywords=kws, on_play=play, on_block=block), "Tame")

for name, atk, hp, cost, text in [
    ("Pack Leader", 2, 4, _cost(wood=1, stone=1), "Pack: +1 ATK per other Animal/Friend."),
    ("Stable Master", 2, 4, _cost(wood=1), "Other Animals and Friends get +1 ATK."),
    ("Best Friends Forever", 3, 5, _cost(wood=2, iron=1), "Pack finisher."),
    ("Sniffer Elder", 3, 6, _cost(wood=1, redstone=1), "When played, gain Diamond if you have a pack."),
]:
    on_play = (lambda obj, state, target_id=None: [mc.gain_materials(state, obj.controller, {"diamond": 1})] if _controlled_count(state, obj.controller, "Animal") >= 3 else []) if name == "Sniffer Elder" else None
    lord = {"subtypes": {"Animal", "Friend"}, "attack": 1} if name == "Stable Master" else None
    _add(make_mob(
        name,
        atk,
        hp,
        cost,
        {"Animal", "Friend"},
        text,
        lord_bonus=lord,
        dynamic_attack_bonus=_pack_bonus if name != "Stable Master" else None,
        on_play=on_play,
    ), "Tame")

for name, cost, effect, text in [
    ("Tame Wolf", _cost(wood=1), _summon_token("Wolf", 3, 2, {"Animal", "Friend"}), "Summon a Wolf."),
    ("Brush the Trail", _cost(wood=1), _two_effects(_gain({"stone": 1}), _draw(1)), "Gain Stone and draw."),
    ("Torchflower Seeds", _cost(wood=1), _gain({"wood": 2}), "Gain 2 Wood."),
    ("Pack Howl", _cost(wood=1, stone=1), _two_effects(_summon_token("Wolf", 3, 2, {"Animal", "Friend"}), _heal(2)), "Summon a Wolf and heal."),
    ("Friendship Feast", _cost(wood=2), _two_effects(_draw(2), _heal(4)), "Draw 2 and heal 4."),
    ("Animal Rescue", _cost(wood=1, redstone=1), _summon_token("Rescued Friend", 2, 4, {"Animal", "Friend"}), "Summon a 2/4 Animal."),
    ("Honey Bottle", _cost(wood=1), _heal(6), "Heal 6."),
    ("Caravan Route", _cost(wood=1, iron=1), _two_effects(_gain({"iron": 1}), _draw(1)), "Gain Iron and draw."),
]:
    _add(make_action(name, cost, text, effect), "Tame")

for name, cost, bonus, slot in [
    ("Brush", _cost(wood=1), {"stone": 1}, "tool"),
    ("Animal Harness", _cost(wood=1, iron=1), {"wood": 1}, "tool"),
    ("Copper Bell", _cost(iron=1, redstone=1), {"redstone": 1}, "tool"),
    ("Friendly Banner", _cost(wood=1, redstone=1), None, "armor"),
]:
    kwargs = {"mining_bonus": bonus} if slot == "tool" else {"armor": 2}
    _add(make_tool(name, slot, cost, "Tame gear.", **kwargs), "Tame")


# ---------------------------------------------------------------------------
# Copper and redstone Pulse
# ---------------------------------------------------------------------------

for name, cost, durability, hook, text in [
    ("Copper Bulb", _cost(iron=1), 3, _pulse(draw=1), "Pulse: draw a card."),
    ("Crafter Array", _cost(wood=1, redstone=1), 4, _pulse(gain={"wood": 1}), "Pulse: gain Wood."),
    ("Observer Chain", _cost(stone=1, redstone=1), 4, _pulse(damage=1), "Pulse: deal 1 to opponent."),
    ("Auto Smelter", _cost(stone=2, redstone=1), 5, _pulse(gain={"iron": 1}), "Pulse: gain Iron."),
    ("Redstone Clock", _cost(stone=1, redstone=1), 4, _pulse(draw=1, damage=1), "Pulse: draw and deal 1."),
    ("Copper Factory", _cost(iron=1, redstone=2), 5, _pulse(gain={"redstone": 1}), "Pulse: refund Redstone."),
    ("Piston Engine", _cost(stone=1, iron=1, redstone=1), 5, _pulse(token=("Piston Drone", 2, 2, {"Construct", "Copper"})), "Pulse: summon a Drone."),
    ("Lightning Rod Tower", _cost(iron=2, redstone=1), 5, _pulse(damage=2), "Pulse: deal 2 to opponent."),
]:
    _add(make_structure(name, durability, cost, {"Structure", "Copper", "Redstone"}, text, on_play=None), "Pulse")
    _cards[-1] = _tag(_attach(_cards[-1], mc_on_event=hook), "Pulse")

for name, atk, hp, cost, hook in [
    ("Copper Golem", 2, 4, _cost(iron=1, redstone=1), _pulse(gain={"stone": 1})),
    ("Redstone Engineer", 1, 3, _cost(wood=1, redstone=1), _pulse(draw=1)),
    ("Piston Drone", 2, 2, _cost(stone=1, redstone=1), _pulse(damage=1)),
    ("Repeater Mage", 3, 3, _cost(wood=1, redstone=1), _pulse(gain={"redstone": 1})),
    ("Comparator Savant", 2, 4, _cost(wood=1, iron=1, redstone=1), _pulse(draw=1, damage=1)),
    ("Copper Sentinel", 4, 4, _cost(iron=2, redstone=1), _pulse(gain={"iron": 1})),
    ("Overclocked Ravager", 5, 4, _cost(iron=1, redstone=2), _pulse(damage=2)),
    ("Redstone Titan", 6, 7, _cost(iron=1, redstone=1), _pulse(draw=1, damage=2)),
]:
    card = make_mob(name, atk, hp, cost, {"Construct", "Copper"}, "Pulse engine.", on_event=hook)
    if name == "Redstone Titan":
        card = _attach(card, mc_on_play=_damage_avatar(3))
    _add(card, "Pulse")

for name, cost, effect, text in [
    ("Redstone Spark", _cost(wood=1), _damage_target(2), "Deal 2."),
    ("Overclock", _cost(redstone=1), _two_effects(_gain({"iron": 1}), _draw(1)), "Gain Iron and draw."),
    ("Copper Oxidation", _cost(wood=1, redstone=1), _damage_target(3), "Deal 3."),
    ("Wax On", _cost(wood=1), _heal(5), "Heal 5."),
    ("Piston Push", _cost(stone=1, redstone=1), _destroy_target("block"), "Destroy a Block."),
    ("Chain Reaction", _cost(redstone=2), _damage_target(5), "Deal 5."),
    ("Automate Mine", _cost(stone=1), _gain({"stone": 1, "iron": 1, "redstone": 1}), "Gain Stone, Iron, Redstone."),
    ("Factory Reset", _cost(iron=1, redstone=1), _draw(2), "Draw 2."),
]:
    _add(make_action(name, cost, text, effect), "Pulse")

for name, slot, cost, attack, bonus, kws in [
    ("Copper Pickaxe", "tool", _cost(wood=1, iron=1), 0, {"iron": 1}, set()),
    ("Redstone Drill", "tool", _cost(iron=1, redstone=1), 0, {"redstone": 1}, set()),
    ("Lightning Trident", "weapon", _cost(iron=1, redstone=2), 5, None, {"ranged"}),
    ("Piston Hammer", "weapon", _cost(iron=2, redstone=1), 5, None, {"siege"}),
]:
    kwargs = {"attack": attack, "mc_keywords": kws} if slot == "weapon" else {"mining_bonus": bonus}
    _add(make_tool(name, slot, cost, "Copper/Redstone gear.", **kwargs), "Pulse")


# ---------------------------------------------------------------------------
# Deep Dark Echo
# ---------------------------------------------------------------------------

for name, cost, durability, hook, bonus in [
    ("Sculk Sensor", _cost(stone=1, redstone=1), 3, _echo_gain(materials={"redstone": 1}), {"redstone": 1}),
    ("Calibrated Sensor", _cost(stone=1, redstone=2), 4, _echo_gain(draw=1), {}),
    ("Sculk Library", _cost(wood=1, redstone=1), 4, _echo_gain(draw=1), {}),
    ("Ancient City Gate", _cost(stone=2, redstone=1), 6, _echo_gain(materials={"iron": 1}), {"iron": 1}),
    ("Echo Shrieker", _cost(stone=1, redstone=1), 3, _echo_gain(token=("Sculk Wisp", 1, 1, {"Sculk"})), {}),
    ("Recovery Compass Shrine", _cost(iron=1, redstone=1), 4, _echo_gain(materials={"diamond": 1}), {}),
]:
    _add(make_structure(name, durability, cost, {"Structure", "Sculk"}, "Echo: death reward.", turn_bonus=bonus), "Echo")
    _cards[-1] = _tag(_attach(_cards[-1], mc_on_event=hook), "Echo")

for name, atk, hp, cost, hook, kws, play in [
    ("Sculk Wisp", 2, 2, _cost(wood=1), _echo_gain(materials={"redstone": 1}), set(), None),
    ("Sculk Crawler", 2, 3, _cost(wood=1, redstone=1), _echo_gain(draw=1), {"climb"}, None),
    ("Echo Bat", 2, 2, _cost(wood=1), _echo_gain(materials={"wood": 1}), {"aerial"}, None),
    ("Deep Dark Stalker", 4, 3, _cost(wood=1, redstone=1), _echo_gain(draw=1), {"climb"}, None),
    ("Shrieker Disciple", 2, 4, _cost(wood=1, redstone=1), _echo_gain(token=("Sculk Wisp", 1, 1, {"Sculk"})), set(), None),
    ("Echo Warden", 6, 7, _cost(iron=1, redstone=1), _echo_gain(draw=1), set(), _damage_target(5)),
    ("Ancient City Warden", 8, 8, _cost(iron=3, redstone=2, diamond=1), _echo_gain(draw=1), set(), _damage_target(5)),
    ("Sonic Boomer", 3, 4, _cost(iron=1, redstone=1), _echo_gain(materials={"redstone": 1}), {"ranged"}, _damage_avatar(1)),
]:
    _add(make_mob(name, atk, hp, cost, {"Hostile", "Sculk"}, "Echo payoff.", mc_keywords=kws, on_play=play, on_event=hook), "Echo")

for name, cost, effect, text in [
    ("Sonic Boom", _cost(redstone=1), _damage_target(5), "Deal 5."),
    ("Sculk Bloom", _cost(redstone=1), _summon_token("Sculk Wisp", 1, 1, {"Sculk"}), "Summon a Sculk Wisp."),
    ("Echo Shards", _cost(stone=1), _two_effects(_gain({"redstone": 1}), _draw(1)), "Gain Redstone and draw."),
    ("Darkness Falls", _cost(redstone=1), _damage_avatar(3), "Deal 3 to opponent avatar."),
    ("Ancient Loot", _cost(iron=1, redstone=1), _two_effects(_gain({"diamond": 1}), _draw(1)), "Gain Diamond and draw."),
    ("Wardens Warning", _cost(redstone=1), _wounded_destroy(3), "Destroy wounded mob with 3 or less remaining HP."),
    ("Skulk the Dead", _cost(redstone=1), _summon_token("Sculk Crawler", 2, 3, {"Sculk", "Hostile"}), "Summon a Sculk Crawler."),
    ("Echo Recovery", _cost(wood=1, redstone=1), _two_effects(_heal(5), _draw(1)), "Heal and draw."),
]:
    _add(make_action(name, cost, text, effect), "Echo")

for name, cost, bonus in [
    ("Echo Compass", _cost(iron=1, redstone=1), {"redstone": 1}),
    ("Swift Sneak Boots", _cost(wood=1, redstone=1), {"stone": 1}),
    ("Ancient Hoe", _cost(wood=1, iron=1), {"wood": 1}),
]:
    _add(make_tool(name, "tool", cost, "Deep Dark tool.", mining_bonus=bonus), "Echo")


# ---------------------------------------------------------------------------
# Nether Bastion Raid
# ---------------------------------------------------------------------------

for name, atk, hp, cost, kws, play, attack in [
    ("Piglin Scout", 2, 2, _cost(wood=1), set(), None, _on_attack_gain({"iron": 1})),
    ("Bastion Brute", 4, 3, _cost(wood=1, iron=1), set(), None, _on_attack_if_raid(1)),
    ("Gold Hoarder", 2, 3, _cost(wood=1, stone=1), set(), _gain({"iron": 1}), None),
    ("Hoglin Charger", 4, 4, _cost(stone=1, iron=1), set(), None, None),
    ("Strider Rider", 3, 3, _cost(wood=1, redstone=1), {"climb"}, None, None),
    ("Magma Runt", 2, 1, _cost(stone=1), set(), None, None),
    ("Nether Raider", 3, 2, _cost(wood=1, iron=1), set(), None, _on_attack_gain({"redstone": 1})),
    ("Bastion Captain", 3, 4, _cost(iron=1, redstone=1), set(), None, None),
    ("Ghast Bombardier", 4, 3, _cost(redstone=2), {"aerial", "ranged"}, None, _on_attack_if_raid(1)),
    ("Wither Raider", 5, 4, _cost(iron=1, redstone=2), set(), _damage_target(2), None),
    ("Piglin Warboss", 5, 5, _cost(wood=1, iron=1), set(), _summon_token("Piglin Scout", 2, 2, {"Raider", "Hostile"}), None),
    ("Netherite Juggernaut", 7, 7, _cost(iron=2, redstone=2, diamond=1), {"siege"}, None, None),
]:
    lord = {"subtypes": {"Raider"}, "attack": 1} if name == "Bastion Captain" else None
    _add(make_mob(
        name,
        atk,
        hp,
        cost,
        {"Hostile", "Raider", "Nether"},
        "Raid pressure.",
        mc_keywords=kws,
        on_play=play,
        on_attack=attack,
        lord_bonus=lord,
        dynamic_attack_bonus=_raid_bonus if name in {"Piglin Warboss", "Netherite Juggernaut"} else None,
    ), "Raid")

for name, cost, durability, bonus, block in [
    ("Bastion Bridge", _cost(stone=1), 4, {"stone": 1}, False),
    ("Piglin Stash", _cost(wood=1, iron=1), 3, {}, False),
    ("Lava Channel", _cost(stone=1, redstone=1), 3, {}, True),
    ("Gold Blockade", _cost(iron=2), 5, {}, True),
    ("Nether Camp", _cost(wood=1, redstone=1), 4, {"redstone": 1}, False),
    ("Raid Banner", _cost(wood=1, iron=1), 4, {}, False),
]:
    _add(make_structure(
        name,
        durability,
        cost,
        {"Block" if block else "Structure", "Raid", "Nether"},
        "Raid support.",
        is_block=block,
        turn_bonus=bonus,
        turn_draw=1 if name == "Piglin Stash" else 0,
        lord_bonus={"subtypes": {"Raider"}, "attack": 1} if name == "Raid Banner" else None,
    ), "Raid")

for name, cost, effect, text in [
    ("Barter for Blades", _cost(wood=1), _two_effects(_gain({"iron": 1}), _draw(1)), "Gain Iron and draw."),
    ("Bastion Ambush", _cost(wood=1, iron=1), _summon_token("Piglin Scout", 2, 2, {"Raider", "Hostile", "Nether"}), "Summon a Piglin."),
    ("Lava Bucket", _cost(stone=1, redstone=1), _damage_target(4), "Deal 4."),
    ("Gold Rush", _cost(iron=1), _gain({"iron": 2}), "Gain 2 Iron."),
    ("Raid the Bed", _cost(iron=1, redstone=1), _damage_target(5), "Deal 5 to target."),
    ("Nether Shortcut", _cost(redstone=1), _two_effects(_gain({"redstone": 1}), _draw(1)), "Gain Redstone and draw."),
    ("Bastion Reinforcements", _cost(wood=1, redstone=1), _summon_token("Bastion Brute", 4, 3, {"Raider", "Hostile", "Nether"}), "Summon a Brute."),
    ("Exploding Bed Trick", _cost(wood=1, redstone=1), _damage_avatar(4), "Deal 4 to opponent avatar."),
]:
    _add(make_action(name, cost, text, effect), "Raid")

for name, slot, cost, attack, kws in [
    ("Golden Axe", "weapon", _cost(iron=1), 3, set()),
    ("Piglin Crossbow", "weapon", _cost(wood=1, iron=1), 4, {"ranged"}),
    ("Netherite Axe", "weapon", _cost(iron=2, redstone=1), 6, {"siege"}),
    ("Soul Speed Boots", "armor", _cost(iron=1, redstone=1), 0, set()),
]:
    kwargs = {"attack": attack, "mc_keywords": kws} if slot == "weapon" else {"armor": 2}
    _add(make_tool(name, slot, cost, "Raid gear.", **kwargs), "Raid")


# ---------------------------------------------------------------------------
# End Voyage and ancient builds
# ---------------------------------------------------------------------------

for name, cost, durability, bonus, draw in [
    ("End Gateway", _cost(stone=2, redstone=1), 5, {"redstone": 1}, 0),
    ("Chorus Grove", _cost(wood=1, diamond=1), 4, {"diamond": 1}, 0),
    ("Purpur Tower", _cost(stone=1, redstone=1), 5, {"redstone": 1}, 0),
    ("End Ship", _cost(wood=1, iron=1, diamond=1), 5, {}, 1),
    ("Dragon Perch", _cost(stone=2, diamond=1), 6, {"diamond": 1}, 0),
    ("Ancient Portal Lab", _cost(iron=1, redstone=1), 4, {"redstone": 1}, 0),
]:
    _add(make_structure(name, durability, cost, {"Structure", "End", "Voyage"}, "Voyage support.", turn_bonus=bonus, turn_draw=draw), "Voyage")

for name, atk, hp, cost, kws, play in [
    ("Enderling", 2, 2, _cost(wood=1), {"climb"}, None),
    ("Chorus Walker", 2, 4, _cost(wood=1, redstone=1), set(), _gain({"redstone": 1})),
    ("End Scout", 2, 2, _cost(wood=1, stone=1), {"aerial"}, _draw(1)),
    ("Shulker Guard", 2, 6, _cost(stone=1, redstone=1), {"reach"}, None),
    ("End Crystal Adept", 3, 3, _cost(redstone=2), {"ranged"}, _damage_avatar(1)),
    ("Purpur Knight", 4, 4, _cost(iron=1, redstone=1), set(), None),
    ("Dragon Herald", 4, 5, _cost(iron=1, diamond=1), {"aerial"}, _gain({"diamond": 1})),
    ("End City Architect", 2, 5, _cost(wood=1, redstone=1), set(), _draw(1)),
    ("Elytra Diver", 3, 2, _cost(wood=1, redstone=1), {"aerial"}, None),
    ("Void Voyager", 5, 5, _cost(redstone=1, diamond=2), {"aerial"}, _draw(2)),
    ("Chorus Dragon", 7, 7, _cost(redstone=1, diamond=1), {"aerial"}, _damage_avatar(3)),
    ("Ender Sovereign", 7, 7, _cost(diamond=1), {"aerial"}, _two_effects(_damage_avatar(3), _draw(1))),
]:
    _add(make_mob(
        name,
        atk,
        hp,
        cost,
        {"Hostile", "End", "Voyage"},
        "Voyage payoff.",
        mc_keywords=kws,
        on_play=play,
        dynamic_attack_bonus=_end_bonus if name in {"Void Voyager", "Chorus Dragon", "Ender Sovereign"} else None,
    ), "Voyage")

for name, cost, effect, text in [
    ("Chorus Fruit", _cost(wood=1), _two_effects(_heal(3), _draw(1)), "Heal and draw."),
    ("Ender Pearl Toss", _cost(redstone=1), _damage_target(3), "Deal 3."),
    ("Locate Stronghold", _cost(redstone=1), _two_effects(_gain({"diamond": 1}), _draw(1)), "Gain Diamond and draw."),
    ("Open End Gateway", _cost(redstone=1, diamond=1), _summon_token("Enderling", 2, 2, {"End", "Voyage", "Hostile"}), "Summon an Enderling."),
    ("Dragon Breath", _cost(redstone=2, diamond=1), _damage_target(6), "Deal 6."),
    ("Shulker Shells", _cost(stone=1, redstone=1), _summon_token("Shulker Guard", 2, 6, {"End", "Voyage"}), "Summon a Shulker Guard."),
    ("Void Map", _cost(wood=1, redstone=1), _explore_any, "Explore a biome."),
    ("Elytra Launch", _cost(wood=1, redstone=1), _summon_token("Elytra Diver", 3, 2, {"End", "Voyage"}), "Summon an Elytra Diver."),
]:
    _add(make_action(name, cost, text, effect), "Voyage")

for name, slot, cost, attack, bonus, kws in [
    ("Chorus Pickaxe", "tool", _cost(wood=1, diamond=1), 0, {"diamond": 1}, set()),
    ("Ender Bow", "weapon", _cost(wood=1, diamond=1), 5, None, {"aerial", "ranged"}),
    ("Elytra Wings", "armor", _cost(redstone=1, diamond=1), 0, None, {"aerial"}),
    ("Dragon Head", "armor", _cost(diamond=2), 0, None, set()),
]:
    kwargs = {"attack": attack, "mc_keywords": kws} if slot == "weapon" else (
        {"mining_bonus": bonus} if slot == "tool" else {"armor": 2, "mc_keywords": kws}
    )
    _add(make_tool(name, slot, cost, "Voyage gear.", **kwargs), "Voyage")


_LIMITED_RELEASE_OMITS = {
    # Designed during the first pass but omitted to keep the expansion inside
    # the requested 150-200 card band. Tokens may still use these names.
    "Wax On",
    "Factory Reset",
    "Ancient Hoe",
    "Swift Sneak Boots",
    "Gold Rush",
    "Soul Speed Boots",
    "Chorus Fruit",
    "Void Map",
    "Elytra Launch",
    "Dragon Head",
}

_cards = [card for card in _cards if card.name not in _LIMITED_RELEASE_OMITS]

MCT_CARDS = {card.name: card for card in _cards}

if not 150 <= len(MCT_CARDS) <= 200:
    raise RuntimeError(f"MCT expansion expected 150-200 unique cards, got {len(MCT_CARDS)}")
