"""
Minecraft TCG alpha rules helpers.

The mode keeps normal Hyperdraft objects/zones for cards and layers a small
Minecraft board model beside them: material stockpiles, biome rows, 4x4 build
grids, avatar gear, and a compact attackers/blockers combat resolver.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Optional

from .types import (
    CardDefinition,
    CardType,
    Characteristics,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    Player,
    ZoneType,
    new_id,
)
from .queries import get_power, get_toughness, has_ability


MATERIALS = ("wood", "stone", "iron", "redstone", "diamond")
GRID_SIZE = 3
STARTING_BIOMES = [
    {"name": "Forest", "yields": {"wood": 1}, "mined": False, "level": 1},
    {"name": "Hills", "yields": {"stone": 1}, "mined": False, "level": 1},
    {"name": "Cave", "yields": {"stone": 1, "iron": 1}, "mined": False, "level": 1},
]
BIOME_UPGRADES = {
    "Forest": {"name": "Old Growth Forest", "yields": {"wood": 2}, "mined": False, "level": 2},
    "Hills": {"name": "Stony Peaks", "yields": {"stone": 2, "iron": 1}, "mined": False, "level": 2},
    "Cave": {"name": "Deep Cave", "yields": {"stone": 1, "iron": 1, "redstone": 1}, "mined": False, "level": 2},
    "Old Growth Forest": {"name": "Woodland Mansion", "yields": {"wood": 2, "redstone": 1}, "mined": False, "level": 3},
    "Stony Peaks": {"name": "Ancient Mountain", "yields": {"stone": 2, "diamond": 1}, "mined": False, "level": 3},
    "Deep Cave": {"name": "Diamond Depths", "yields": {"stone": 1, "iron": 1, "diamond": 1}, "mined": False, "level": 3},
}


def empty_materials() -> dict[str, int]:
    return {m: 0 for m in MATERIALS}


def empty_grid() -> list[list[Optional[str]]]:
    return [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]


def ensure_player_state(state: GameState, player_id: str) -> None:
    player = state.players.get(player_id)
    if not player:
        return

    if not isinstance(player.mc_materials, dict) or not player.mc_materials:
        player.mc_materials = empty_materials()
    else:
        for material in MATERIALS:
            player.mc_materials[material] = int(player.mc_materials.get(material, 0) or 0)

    if not isinstance(player.mc_avatar_gear, dict) or not player.mc_avatar_gear:
        player.mc_avatar_gear = {"weapon": None, "armor": None, "tool": None}
    for slot in ("weapon", "armor", "tool"):
        player.mc_avatar_gear.setdefault(slot, None)

    state.minecraft_biomes.setdefault(
        player_id,
        [dict(slot, yields=dict(slot["yields"])) for slot in STARTING_BIOMES],
    )
    state.minecraft_grid.setdefault(player_id, empty_grid())


def setup_minecraft_player(game, player: Player) -> None:
    player.life = 20
    player.max_life = 20
    player.has_lost = False
    player.mc_avatar_action_used = False
    player.mc_avatar_exhausted = False
    player.mc_materials = empty_materials()
    player.mc_avatar_gear = {"weapon": None, "armor": None, "tool": None}
    ensure_player_state(game.state, player.id)


def reset_for_turn(state: GameState, player_id: str) -> None:
    ensure_player_state(state, player_id)
    player = state.players.get(player_id)
    if player:
        player.mc_avatar_action_used = False
        player.mc_avatar_exhausted = False

    for biome in state.minecraft_biomes.get(player_id, []):
        biome["mined"] = False

    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in list(battlefield.objects):
            obj = state.objects.get(oid)
            if obj and obj.controller == player_id and CardType.MC_MOB in obj.characteristics.types:
                obj.state.tapped = False
                obj.state.mc_exhausted = False
                obj.state.attacking = False
                obj.state.blocking = False
                obj.state.summoning_sickness = False

    state.turn_data[f"mc_first_mine_used_{player_id}"] = False
    state.turn_data[f"mc_day_craft_discount_used_{player_id}"] = False


def apply_start_turn_bonuses(game, player_id: str) -> list[Event]:
    """Apply persistent Minecraft structure bonuses at the start of a turn,
    plus Phyrexian upkeep tax (1 dmg per Compleated mob you control)."""
    state = game.state
    ensure_player_state(state, player_id)
    events: list[Event] = []
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return events

    compleated_count = 0
    for oid in list(battlefield.objects):
        obj = state.objects.get(oid)
        if not obj or obj.controller != player_id or obj.zone != ZoneType.BATTLEFIELD:
            continue
        if not obj.card_def:
            continue
        bonus = getattr(obj.card_def, "mc_turn_bonus", None)
        if isinstance(bonus, dict) and bonus:
            event = gain_materials(state, player_id, bonus)
            event.source = obj.id
            game.emit(event)
            events.append(event)
        draw_count = int(getattr(obj.card_def, "mc_turn_draw", 0) or 0)
        if draw_count > 0:
            event = Event(type=EventType.DRAW, payload={"player": player_id, "count": draw_count}, source=obj.id)
            game.emit(event)
            events.append(event)
        if "Compleated" in obj.characteristics.subtypes and CardType.MC_MOB in obj.characteristics.types:
            compleated_count += 1

    if compleated_count > 0:
        oil_event = Event(
            type=EventType.DAMAGE,
            payload={"target": player_id, "amount": compleated_count, "source": player_id, "is_combat": False, "reason": "compleated_upkeep"},
        )
        game.emit(oil_event)
        events.append(oil_event)
        game.check_state_based_actions()
        events.extend(handle_avatar_deaths(game))
    return events


def maybe_flip_day_night(state: GameState, active_player_id: str) -> Optional[Event]:
    player_count = max(1, len(state.players))
    state.minecraft_round_turns += 1
    if state.minecraft_round_turns <= 1:
        return None
    if (state.minecraft_round_turns - 1) % player_count != 0:
        return None
    state.minecraft_day_phase = "night" if state.minecraft_day_phase == "day" else "day"
    return Event(
        type=EventType.MC_DAY_NIGHT_FLIP,
        payload={"phase": state.minecraft_day_phase, "player": active_player_id},
    )


def cleanup_references(state: GameState) -> None:
    for pid, grid in list(state.minecraft_grid.items()):
        for y, row in enumerate(grid):
            for x, oid in enumerate(row):
                obj = state.objects.get(oid) if oid else None
                if not obj or obj.zone != ZoneType.BATTLEFIELD:
                    row[x] = None
                    if obj:
                        obj.state.mc_grid_x = None
                        obj.state.mc_grid_y = None

    for player in state.players.values():
        for slot, oid in list(player.mc_avatar_gear.items()):
            obj = state.objects.get(oid) if oid else None
            if not obj or obj.zone != ZoneType.BATTLEFIELD:
                player.mc_avatar_gear[slot] = None
                if obj:
                    obj.state.mc_gear_slot = None


def card_material_cost(card_def: CardDefinition | None) -> dict[str, int]:
    raw = getattr(card_def, "mc_cost", None)
    if not isinstance(raw, dict):
        return {}
    return {m: max(0, int(raw.get(m, 0) or 0)) for m in MATERIALS if int(raw.get(m, 0) or 0) > 0}


def _discounted_cost(state: GameState, player_id: str, obj: GameObject) -> dict[str, int]:
    cost = dict(card_material_cost(obj.card_def))
    if state.minecraft_day_phase != "day":
        return cost
    if not (CardType.MC_STRUCTURE in obj.characteristics.types or CardType.MC_BLOCK in obj.characteristics.types):
        return cost
    key = f"mc_day_craft_discount_used_{player_id}"
    if state.turn_data.get(key):
        return cost
    for material in ("wood", "stone"):
        if cost.get(material, 0) > 0:
            cost[material] -= 1
            if cost[material] <= 0:
                cost.pop(material, None)
            return cost
    return cost


def can_pay(state: GameState, player_id: str, cost: dict[str, int]) -> bool:
    player = state.players.get(player_id)
    if not player:
        return False
    ensure_player_state(state, player_id)
    return all(player.mc_materials.get(m, 0) >= amount for m, amount in cost.items())


def pay_materials(state: GameState, player_id: str, cost: dict[str, int]) -> bool:
    if not can_pay(state, player_id, cost):
        return False
    player = state.players[player_id]
    for material, amount in cost.items():
        player.mc_materials[material] -= amount
    return True


def gain_materials(state: GameState, player_id: str, gains: dict[str, int]) -> Event:
    ensure_player_state(state, player_id)
    player = state.players[player_id]
    normalized = {}
    for material, amount in gains.items():
        if material not in MATERIALS:
            continue
        value = max(0, int(amount or 0))
        if value:
            player.mc_materials[material] += value
            normalized[material] = value
    return Event(type=EventType.MC_MATERIAL_GAIN, payload={"player": player_id, "materials": normalized})


def _move_object(game, obj: GameObject, to_zone: ZoneType, source: Optional[str] = None) -> list[Event]:
    from_zone = obj.zone
    payload = {
        "object_id": obj.id,
        "from_zone_type": from_zone,
        "to_zone_type": to_zone,
    }
    if from_zone in {ZoneType.HAND, ZoneType.LIBRARY, ZoneType.GRAVEYARD}:
        payload["from_zone"] = f"{from_zone.name.lower()}_{obj.owner}"
    if to_zone in {ZoneType.HAND, ZoneType.LIBRARY, ZoneType.GRAVEYARD}:
        payload["to_zone"] = f"{to_zone.name.lower()}_{obj.owner}"
    elif to_zone in {ZoneType.BATTLEFIELD, ZoneType.EXILE, ZoneType.COMMAND}:
        payload["to_zone"] = to_zone.name.lower()
    event = Event(type=EventType.ZONE_CHANGE, payload=payload, source=source or obj.id, controller=obj.controller)
    return game.emit(event)


def _coerce_cell(cell: Any) -> Optional[tuple[int, int]]:
    if isinstance(cell, dict):
        x, y = cell.get("x"), cell.get("y")
    elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
        x, y = cell[0], cell[1]
    else:
        return None
    try:
        ix, iy = int(x), int(y)
    except Exception:
        return None
    if 0 <= ix < GRID_SIZE and 0 <= iy < GRID_SIZE:
        return ix, iy
    return None


def play_card(
    game,
    player_id: str,
    card_id: str,
    cell: Any = None,
    target_id: Optional[str] = None,
    target_column: Optional[int] = None,
) -> tuple[bool, str, list[Event]]:
    state = game.state
    ensure_player_state(state, player_id)
    obj = state.objects.get(card_id)
    hand = state.zones.get(f"hand_{player_id}")
    if not obj or not hand or card_id not in hand.objects:
        return False, "Card is not in hand", []
    if obj.controller != player_id:
        return False, "You do not control that card", []

    # If frontend passed a column for an action card's target, resolve it.
    if isinstance(target_column, int) and not target_id:
        opponent = next((pid for pid in state.players if pid != player_id and not state.players[pid].has_lost), None)
        if opponent:
            target_id = column_target(state, opponent, target_column) or opponent

    types = obj.characteristics.types
    if CardType.MC_STRUCTURE in types or CardType.MC_BLOCK in types:
        pos = _coerce_cell(cell)
        if pos is None:
            return False, "A grid cell is required", []
        x, y = pos
        if state.minecraft_grid[player_id][y][x] is not None:
            return False, "Grid cell is occupied", []

    cost = _discounted_cost(state, player_id, obj)
    if not pay_materials(state, player_id, cost):
        return False, "Not enough materials", []

    spend_ev = Event(type=EventType.MC_MATERIAL_SPEND, payload={"player": player_id, "materials": dict(cost)}, source=card_id)
    game.emit(spend_ev)
    events: list[Event] = [spend_ev]
    if state.minecraft_day_phase == "day" and (CardType.MC_STRUCTURE in types or CardType.MC_BLOCK in types):
        state.turn_data[f"mc_day_craft_discount_used_{player_id}"] = True

    if CardType.MC_ACTION in types:
        events.append(Event(type=EventType.MC_PLAY_CARD, payload={"player": player_id, "card_id": card_id}, source=card_id))
        on_play = getattr(obj.card_def, "mc_on_play", None)
        if callable(on_play):
            for ev in on_play(obj, state, target_id):
                game.emit(ev)
                events.append(ev)
        events.extend(_move_object(game, obj, ZoneType.GRAVEYARD, source=card_id))
        cleanup_references(state)
        return True, "Action resolved", events

    if CardType.MC_STRUCTURE in types or CardType.MC_BLOCK in types:
        grid = state.minecraft_grid[player_id]
        events.extend(_move_object(game, obj, ZoneType.BATTLEFIELD, source=card_id))
        obj.state.mc_grid_x = x
        obj.state.mc_grid_y = y
        grid[y][x] = obj.id
        events.append(Event(
            type=EventType.MC_GRID_PLACE,
            payload={"player": player_id, "object_id": obj.id, "x": x, "y": y},
            source=card_id,
        ))
    elif CardType.MC_TOOL in types:
        slot = getattr(obj.card_def, "mc_tool_slot", None) or "tool"
        if slot not in {"weapon", "armor", "tool"}:
            slot = "tool"
        old_id = state.players[player_id].mc_avatar_gear.get(slot)
        if old_id and old_id in state.objects:
            events.extend(_move_object(game, state.objects[old_id], ZoneType.GRAVEYARD, source=card_id))
        events.extend(_move_object(game, obj, ZoneType.BATTLEFIELD, source=card_id))
        obj.state.mc_gear_slot = slot
        state.players[player_id].mc_avatar_gear[slot] = obj.id
    else:
        events.extend(_move_object(game, obj, ZoneType.BATTLEFIELD, source=card_id))
        obj.state.summoning_sickness = True

    events.append(Event(type=EventType.MC_PLAY_CARD, payload={"player": player_id, "card_id": card_id}, source=card_id))
    on_play = getattr(obj.card_def, "mc_on_play", None)
    if callable(on_play):
        for ev in on_play(obj, state, target_id):
            game.emit(ev)
            events.append(ev)
    cleanup_references(state)
    return True, "Card played", events


def _first_yield_material(biome: dict[str, Any]) -> Optional[str]:
    yields = biome.get("yields") or {}
    for material in MATERIALS:
        if int(yields.get(material, 0) or 0) > 0:
            return material
    return None


def mine_biome(game, player_id: str, biome_index: int, actor_id: Optional[str] = None, *, avatar: bool = False) -> tuple[bool, str, list[Event]]:
    state = game.state
    ensure_player_state(state, player_id)
    player = state.players.get(player_id)
    if not player:
        return False, "Player not found", []
    if biome_index < 0 or biome_index >= len(state.minecraft_biomes[player_id]):
        return False, "Invalid biome", []
    biome = state.minecraft_biomes[player_id][biome_index]
    if biome.get("mined"):
        return False, "Biome already mined this turn", []

    if avatar:
        if player.mc_avatar_action_used:
            return False, "Avatar action already used", []
        player.mc_avatar_action_used = True
        player.mc_avatar_exhausted = True
        tool_id = player.mc_avatar_gear.get("tool")
        tool = state.objects.get(tool_id) if tool_id else None
        bonus = getattr(tool.card_def, "mc_mining_bonus", None) if tool and tool.card_def else None
    else:
        actor = state.objects.get(actor_id or "")
        if not actor or actor.controller != player_id or actor.zone != ZoneType.BATTLEFIELD:
            return False, "Worker not found", []
        if CardType.MC_MOB not in actor.characteristics.types or "Worker" not in actor.characteristics.subtypes:
            return False, "Only Worker mobs can mine", []
        if actor.state.tapped or actor.state.mc_exhausted:
            return False, "Worker is exhausted", []
        if actor.state.summoning_sickness:
            return False, "Worker is not ready", []
        actor.state.tapped = True
        actor.state.mc_exhausted = True
        bonus = getattr(actor.card_def, "mc_mining_bonus", None) if actor.card_def else None

    gains = {m: int(v or 0) for m, v in (biome.get("yields") or {}).items() if m in MATERIALS and int(v or 0) > 0}
    if isinstance(bonus, dict):
        for material, amount in bonus.items():
            if material in MATERIALS:
                gains[material] = gains.get(material, 0) + int(amount or 0)
    elif isinstance(bonus, str) and bonus in MATERIALS:
        gains[bonus] = gains.get(bonus, 0) + 1

    first_mine_key = f"mc_first_mine_used_{player_id}"
    if state.minecraft_day_phase == "day" and not state.turn_data.get(first_mine_key):
        material = _first_yield_material(biome)
        if material:
            gains[material] = gains.get(material, 0) + 1
        state.turn_data[first_mine_key] = True

    biome["mined"] = True
    gain_event = gain_materials(state, player_id, gains)
    marker = Event(
        type=EventType.MC_ASSIGN_WORKER if not avatar else EventType.MC_AVATAR_ACTION,
        payload={"player": player_id, "actor_id": actor_id, "biome_index": biome_index, "materials": gains},
        source=actor_id,
    )
    game.emit(gain_event)
    return True, "Mined biome", [marker, gain_event]


def explore_biome(game, player_id: str, biome_index: int) -> tuple[bool, str, list[Event]]:
    state = game.state
    ensure_player_state(state, player_id)
    player = state.players.get(player_id)
    if not player:
        return False, "Player not found", []
    if player.mc_avatar_action_used:
        return False, "Avatar action already used", []
    if biome_index < 0 or biome_index >= len(state.minecraft_biomes[player_id]):
        return False, "Invalid biome", []
    current = state.minecraft_biomes[player_id][biome_index]
    replacement = BIOME_UPGRADES.get(current.get("name"))
    if not replacement:
        return False, "Biome cannot be upgraded further", []
    state.minecraft_biomes[player_id][biome_index] = dict(replacement, yields=dict(replacement["yields"]))
    player.mc_avatar_action_used = True
    player.mc_avatar_exhausted = True
    event = Event(
        type=EventType.MC_EXPLORE_BIOME,
        payload={"player": player_id, "biome_index": biome_index, "biome": state.minecraft_biomes[player_id][biome_index]},
    )
    game.emit(event)
    return True, "Biome explored", [event]


def avatar_attack(
    game,
    player_id: str,
    target_id: Optional[str] = None,
    *,
    target_column: Optional[int] = None,
) -> tuple[bool, str, list[Event]]:
    state = game.state
    player = state.players.get(player_id)
    if not player:
        return False, "Player not found", []
    if player.mc_avatar_action_used:
        return False, "Avatar action already used", []
    opponent = next((pid for pid in state.players if pid != player_id and not state.players[pid].has_lost), None)
    if not opponent:
        return False, "No opponent", []
    weapon_id = player.mc_avatar_gear.get("weapon")
    weapon = state.objects.get(weapon_id) if weapon_id else None
    amount = int(getattr(weapon.card_def, "mc_attack", 1) or 1) if weapon and weapon.card_def else 1
    weapon_keywords: set[str] = set()
    if weapon and weapon.card_def:
        weapon_keywords = {str(k).lower() for k in (getattr(weapon.card_def, "mc_keywords", None) or ())}
    # Resolve final target
    resolved = target_id
    if isinstance(target_column, int) and 0 <= target_column < GRID_SIZE:
        resolved = column_target(state, opponent, target_column, weapon_keywords) or opponent
    elif resolved == opponent or resolved is None:
        resolved = opponent
    elif resolved not in state.objects:
        resolved = opponent
    player.mc_avatar_action_used = True
    player.mc_avatar_exhausted = True
    damage = Event(type=EventType.DAMAGE, payload={"target": resolved, "amount": amount, "source": weapon_id or player_id}, source=weapon_id)
    game.emit(damage)
    marker = Event(type=EventType.MC_AVATAR_ACTION, payload={"player": player_id, "kind": "attack", "target": resolved, "amount": amount}, source=weapon_id)
    game.check_state_based_actions()
    handle_avatar_deaths(game)
    return True, "Avatar attacked", [marker, damage]


OIL_COUNTERS_TO_LOSE = 5


def _apply_infect(
    state: GameState,
    attacker: Optional[GameObject],
    target_id: Optional[str],
    amount: int,
    defender_id: str,
) -> None:
    """Deposit oil counters on the defender's avatar when an infect attacker
    deals damage to the avatar (or grid object — current rule is avatar only)."""
    if not attacker or amount <= 0:
        return
    if "infect" not in mc_keywords_of(attacker):
        return
    if target_id != defender_id:
        return
    defender = state.players.get(defender_id)
    if not defender:
        return
    defender.mc_oil_counters = (getattr(defender, "mc_oil_counters", 0) or 0) + amount


def glistening_oil_convert(state: GameState, controller: str, target_id: str) -> bool:
    """Convert an opponent mob with HP <= 2 to your side as Compleated.
    Returns True if the conversion succeeded."""
    target = state.objects.get(target_id)
    if not target or target.controller == controller:
        return False
    if CardType.MC_MOB not in target.characteristics.types:
        return False
    remaining = max(0, int(target.characteristics.toughness or 0) - int(target.state.damage or 0))
    if remaining > 2:
        return False
    target.controller = controller
    target.characteristics.subtypes.add("Compleated")
    target.state.summoning_sickness = True
    target.state.tapped = False
    target.state.mc_exhausted = False
    return True


def has_bed(state: GameState, player_id: str) -> bool:
    grid = state.minecraft_grid.get(player_id) or []
    for row in grid:
        for oid in row:
            obj = state.objects.get(oid) if oid else None
            if obj and obj.zone == ZoneType.BATTLEFIELD and "Bed" in obj.characteristics.subtypes:
                return True
    return False


def discard_avatar_gear(game, player_id: str) -> list[Event]:
    events: list[Event] = []
    player = game.state.players.get(player_id)
    if not player:
        return events
    for slot, oid in list(player.mc_avatar_gear.items()):
        obj = game.state.objects.get(oid) if oid else None
        if obj and obj.zone == ZoneType.BATTLEFIELD:
            events.extend(_move_object(game, obj, ZoneType.GRAVEYARD, source=oid))
        player.mc_avatar_gear[slot] = None
    cleanup_references(game.state)
    return events


def handle_avatar_deaths(game) -> list[Event]:
    events: list[Event] = []
    for player in list(game.state.players.values()):
        if player.has_lost:
            continue
        # Phyrexian compleation loss: 5+ oil counters means the avatar has been
        # turned into a Phyrexian and the player loses regardless of HP.
        if (getattr(player, "mc_oil_counters", 0) or 0) >= OIL_COUNTERS_TO_LOSE:
            player.has_lost = True
            event = Event(type=EventType.PLAYER_LOSES, payload={"player": player.id, "reason": "compleated"})
            game.emit(event)
            events.append(event)
            continue
        if player.life > 0:
            continue
        if has_bed(game.state, player.id):
            events.extend(discard_avatar_gear(game, player.id))
            player.life = 20
            event = Event(type=EventType.MC_RESPAWN, payload={"player": player.id, "life": 20})
            game.emit(event)
            events.append(event)
        else:
            player.has_lost = True
            event = Event(type=EventType.PLAYER_LOSES, payload={"player": player.id, "reason": "avatar_no_bed"})
            game.emit(event)
            events.append(event)
    return events


def object_cell(state: GameState, object_id: str) -> Optional[tuple[str, int, int]]:
    obj = state.objects.get(object_id)
    if not obj:
        return None
    x, y = obj.state.mc_grid_x, obj.state.mc_grid_y
    if x is None or y is None:
        return None
    return obj.controller, int(x), int(y)


def mc_keywords_of(obj: Optional[GameObject]) -> set[str]:
    if not obj or not obj.card_def:
        return set()
    raw = getattr(obj.card_def, "mc_keywords", None) or ()
    return {str(k).lower() for k in raw}


def column_target(
    state: GameState,
    defender_id: str,
    column: int,
    attacker_keywords: set[str] | None = None,
) -> Optional[str]:
    """Return the object_id of the frontmost occupant in the given column, or
    None if the column is clear (so the avatar takes the hit).

    Aerial bypasses Block-typed cards. Climb additionally bypasses Walls.
    """
    grid = state.minecraft_grid.get(defender_id)
    if not grid:
        return None
    if not isinstance(column, int) or not (0 <= column < GRID_SIZE):
        return None
    keywords = attacker_keywords or set()
    has_aerial = "aerial" in keywords
    has_climb = "climb" in keywords
    for y in range(GRID_SIZE - 1, -1, -1):  # front (high y) to back (low y)
        oid = grid[y][column]
        if not oid:
            continue
        obj = state.objects.get(oid)
        if not obj:
            continue
        is_block = CardType.MC_BLOCK in obj.characteristics.types
        if has_aerial and is_block:
            continue
        if has_climb and "Wall" in obj.characteristics.subtypes:
            continue
        return oid
    return None


def exposed_grid_targets(state: GameState, player_id: str) -> list[str]:
    """Frontmost-per-column targets a vanilla attacker can hit (no keywords)."""
    cleanup_references(state)
    out = []
    for column in range(GRID_SIZE):
        oid = column_target(state, player_id, column)
        if oid:
            out.append(oid)
    return out


def column_for_object(state: GameState, object_id: str) -> Optional[int]:
    cell = object_cell(state, object_id)
    return cell[1] if cell else None


def is_exposed_grid_object(state: GameState, object_id: str) -> bool:
    """Backward-compat shim: True if this object is the frontmost in its column."""
    cell = object_cell(state, object_id)
    if cell is None:
        return False
    player_id, x, _y = cell
    return column_target(state, player_id, x) == object_id


def _mob_attack_power(obj: GameObject, state: GameState) -> int:
    power = int(get_power(obj, state) or 0)
    subtypes = obj.characteristics.subtypes
    if state.minecraft_day_phase == "night" and "Hostile" in subtypes:
        power += 1
    bonus_fn = getattr(obj.card_def, "mc_dynamic_attack_bonus", None) if obj.card_def else None
    if callable(bonus_fn):
        power += int(bonus_fn(obj, state) or 0)
    # Lord effects: any other on-battlefield mob with mc_lord_bonus matching us.
    battlefield = state.zones.get("battlefield")
    if battlefield:
        for oid in battlefield.objects:
            if oid == obj.id:
                continue
            other = state.objects.get(oid)
            if not other or other.controller != obj.controller or not other.card_def:
                continue
            lord = getattr(other.card_def, "mc_lord_bonus", None)
            if not lord:
                continue
            req_subtypes = lord.get("subtypes") or set()
            if req_subtypes and not (set(req_subtypes) & set(subtypes)):
                continue
            power += int(lord.get("attack", 0) or 0)
    return max(0, power)


def _resolve_attack_target(
    state: GameState,
    defender_id: str,
    attacker: Optional[GameObject],
    target_column: Optional[int],
) -> tuple[Optional[int], str]:
    """Pick the column and resolved target_id for an attacker.

    Returns (column, target_id). target_id is either the frontmost in column
    (with attacker keywords applied), or the defender's avatar id when the
    column is clear.
    """
    keywords = mc_keywords_of(attacker)
    if isinstance(target_column, int) and 0 <= target_column < GRID_SIZE:
        return target_column, column_target(state, defender_id, target_column, keywords) or defender_id
    # No column specified: pick the column with the bed first, else the
    # weakest-defended column.
    grid = state.minecraft_grid.get(defender_id) or []
    bed_col: Optional[int] = None
    for column in range(GRID_SIZE):
        oid = column_target(state, defender_id, column, keywords)
        if oid:
            obj = state.objects.get(oid)
            if obj and "Bed" in obj.characteristics.subtypes:
                bed_col = column
                break
    if bed_col is not None:
        return bed_col, column_target(state, defender_id, bed_col, keywords) or defender_id
    for column in range(GRID_SIZE):
        if column_target(state, defender_id, column, keywords) is None:
            return column, defender_id
    # Every column has a defender; just pick column 0.
    return 0, column_target(state, defender_id, 0, keywords) or defender_id


def legal_blockers(state: GameState, defender_id: str) -> list[GameObject]:
    battlefield = state.zones.get("battlefield")
    if not battlefield:
        return []
    return [
        state.objects[oid]
        for oid in battlefield.objects
        if oid in state.objects
        and state.objects[oid].controller == defender_id
        and CardType.MC_MOB in state.objects[oid].characteristics.types
        and not state.objects[oid].state.tapped
        and not state.objects[oid].state.mc_exhausted
    ]


def can_block(blocker: Optional[GameObject], attacker: Optional[GameObject]) -> bool:
    """Aerial attackers can only be blocked by aerial or reach defenders."""
    if not blocker or not attacker:
        return False
    attacker_kw = mc_keywords_of(attacker)
    if "aerial" not in attacker_kw:
        return True
    blocker_kw = mc_keywords_of(blocker)
    return "aerial" in blocker_kw or "reach" in blocker_kw


def legal_blockers_for(state: GameState, defender_id: str, attacker_id: str) -> list[GameObject]:
    """Subset of legal_blockers that can legally block this specific attacker."""
    attacker = state.objects.get(attacker_id)
    return [b for b in legal_blockers(state, defender_id) if can_block(b, attacker)]


def auto_blockers(state: GameState, defender_id: str, attackers: list[dict[str, Any]]) -> dict[str, str]:
    """Smarter AI block selection.

    Priorities:
      1. If avatar is at lethal risk and defender has no Bed, block any attacker
         that can be blocked, with the smallest viable blocker (preserve other
         defenders for later).
      2. Otherwise, only block when the trade is good — kill the attacker, or
         block a high-threat (avatar / Bed-aimed) hit even at the cost of the
         blocker.
      3. Never block when the blocker dies and the attacker survives unscathed
         and isn't aimed at avatar/Bed.
    """
    defender = state.players.get(defender_id)
    blockers = legal_blockers(state, defender_id)
    if not blockers or not attackers:
        return {}
    has_bed_now = has_bed(state, defender_id)

    def attacker_power(a) -> int:
        obj = state.objects.get(a["attacker_id"])
        return _mob_attack_power(obj, state) if obj else 0

    def attack_target_id(a) -> Optional[str]:
        attacker = state.objects.get(a["attacker_id"])
        if not attacker:
            return None
        column = a.get("target_column")
        if not isinstance(column, int):
            return defender_id
        return column_target(state, defender_id, column, mc_keywords_of(attacker)) or defender_id

    def threat_score(a) -> int:
        target = attack_target_id(a)
        target_obj = state.objects.get(target) if target and target != defender_id else None
        base = attacker_power(a)
        if target == defender_id:
            return 1000 + base  # avatar damage = top priority
        if target_obj and "Bed" in target_obj.characteristics.subtypes:
            return 800 + base
        return 100 + base

    # Total avatar damage incoming if we don't block.
    incoming_avatar_damage = sum(
        attacker_power(a) for a in attackers if attack_target_id(a) == defender_id
    )
    avatar_lethal = (
        defender is not None
        and not has_bed_now
        and incoming_avatar_damage >= int(defender.life or 0)
    )

    sorted_attacks = sorted(attackers, key=threat_score, reverse=True)
    assignments: dict[str, str] = {}
    used: set[str] = set()

    for attack in sorted_attacks:
        attacker = state.objects.get(attack["attacker_id"])
        if not attacker:
            continue
        attacker_kw = mc_keywords_of(attacker)
        a_pow = _mob_attack_power(attacker, state)
        a_tough_remaining = max(0, int(get_toughness(attacker, state) or 0) - int(attacker.state.damage or 0))

        target = attack_target_id(attack)
        hits_avatar = (target == defender_id)
        target_obj = state.objects.get(target) if target and target != defender_id else None
        hits_bed = bool(target_obj and "Bed" in target_obj.characteristics.subtypes)

        # Find the best legal blocker.
        best_id: Optional[str] = None
        best_score = -10**9
        for blocker in blockers:
            if blocker.id in used or not can_block(blocker, attacker):
                continue
            b_pow = int(get_power(blocker, state) or 0)
            b_hp = max(0, int(get_toughness(blocker, state) or 0) - int(blocker.state.damage or 0))
            b_value = b_pow + b_hp
            blocker_dies = b_hp <= a_pow
            attacker_dies = (
                "ranged" not in attacker_kw
                and b_pow >= a_tough_remaining
                and a_tough_remaining > 0
            )

            score = 0
            if avatar_lethal and hits_avatar:
                score += 5000
            if hits_avatar:
                score += 200
            if hits_bed:
                score += 120
            if attacker_dies and not blocker_dies:
                score += 90
            elif attacker_dies and blocker_dies:
                # Mutual kill: good if we trade up, bad if we trade down.
                score += 30 + (a_pow + a_tough_remaining) - b_value
            elif blocker_dies and not attacker_dies:
                # Chump block: only OK if attacker is aimed at avatar/Bed.
                if hits_avatar or hits_bed:
                    score += 20 - b_value // 2
                else:
                    score -= 1000  # don't waste defenders on grid bumps
            else:
                # Both survive: small value if we kill nothing meaningful.
                score += 5 + min(a_pow, b_hp) - max(0, b_pow - a_tough_remaining)
            # Prefer smaller blockers to absorb so big mobs survive.
            score -= b_value // 4

            if score > best_score:
                best_score = score
                best_id = blocker.id

        if best_id is not None and best_score > 0:
            assignments[attack["attacker_id"]] = best_id
            used.add(best_id)

    return assignments


def _column_from_raw(raw: dict[str, Any], state: GameState, defender_id: str) -> Optional[int]:
    """Extract a column index from either target_column or a legacy target_id."""
    raw_col = raw.get("target_column")
    if isinstance(raw_col, int) and 0 <= raw_col < GRID_SIZE:
        return raw_col
    if isinstance(raw_col, str):
        try:
            n = int(raw_col)
        except (TypeError, ValueError):
            n = -1
        if 0 <= n < GRID_SIZE:
            return n
    legacy = raw.get("target_id") or raw.get("target")
    if not legacy or legacy == defender_id:
        return None
    cell = object_cell(state, str(legacy))
    if cell and cell[0] == defender_id:
        return cell[1]
    return None


def declare_attackers(
    game,
    player_id: str,
    attacks: list[dict[str, Any]],
    *,
    auto_block: bool = True,
) -> tuple[bool, str, list[Event]]:
    state = game.state
    if state.active_player != player_id:
        return False, "Not your turn", []
    defender_id = next((pid for pid in state.players if pid != player_id and not state.players[pid].has_lost), None)
    if not defender_id:
        return False, "No defender", []
    valid_attacks: list[dict[str, Any]] = []
    on_attack_events: list[Event] = []
    for raw in attacks:
        attacker_id = raw.get("attacker_id") or raw.get("id")
        attacker = state.objects.get(attacker_id)
        if not attacker or attacker.controller != player_id or attacker.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.MC_MOB not in attacker.characteristics.types:
            continue
        if attacker.state.tapped or attacker.state.mc_exhausted:
            continue
        if attacker.state.summoning_sickness and not has_ability(attacker, "haste", state):
            continue
        target_column = _column_from_raw(raw, state, defender_id)
        column, target_id = _resolve_attack_target(state, defender_id, attacker, target_column)
        attacker.state.tapped = True
        attacker.state.mc_exhausted = True
        attacker.state.attacking = True
        attacker.state.mc_last_attack_column = column
        attacker.state.mc_last_attack_target = target_id
        valid_attacks.append({
            "attacker_id": attacker_id,
            "target_id": target_id,
            "target_column": column,
        })
        on_attack = getattr(attacker.card_def, "mc_on_attack", None) if attacker.card_def else None
        if callable(on_attack):
            for ev in on_attack(attacker, state, target_id) or []:
                game.emit(ev)
                on_attack_events.append(ev)
    if not valid_attacks:
        return False, "No legal attackers", []

    state.minecraft_combat = {
        "phase": "declare_blockers",
        "attacking_player": player_id,
        "defending_player": defender_id,
        "attackers": list(valid_attacks),
        "blockers": [],
        "legal_blockers": [obj.id for obj in legal_blockers(state, defender_id)],
    }
    attack_event = Event(type=EventType.MC_DECLARE_ATTACKERS, payload=state.minecraft_combat, controller=player_id)
    game.emit(attack_event)
    pre_events = on_attack_events + [attack_event]
    if not auto_block:
        return True, "Awaiting blockers", pre_events

    # Prefer the defending seat's AI handler if one is attached, so per-seat
    # bias presets (e.g. block_mode="chump_anything", "never") apply on this
    # auto_block path the same way they do on the explicit declare_blockers
    # prompt path. Falls back to the smart engine default when no handler is
    # available. Mirrors MinecraftTurnManager._run_pending_block_prompt.
    handler = getattr(getattr(game, "turn_manager", None), "minecraft_ai_handler", None)
    choose = getattr(handler, "choose_blockers", None) if handler else None
    if callable(choose):
        block_map = choose(state, defender_id, valid_attacks)
    else:
        block_map = auto_blockers(state, defender_id, valid_attacks)
    ok, msg, evs = resolve_combat(game, player_id, defender_id, valid_attacks, block_map)
    if ok:
        evs = pre_events + evs
    return ok, msg, evs


def declare_blockers(game, defender_id: str, blockers: list[dict[str, Any]]) -> tuple[bool, str, list[Event]]:
    state = game.state
    combat = state.minecraft_combat or {}
    if combat.get("phase") != "declare_blockers":
        return False, "No blocks are being declared", []
    if combat.get("defending_player") != defender_id:
        return False, "You are not the defending player", []

    attacks = list(combat.get("attackers") or [])
    attacker_ids = {a.get("attacker_id") for a in attacks}
    legal_ids = {obj.id for obj in legal_blockers(state, defender_id)}
    used_blockers: set[str] = set()
    block_map: dict[str, str] = {}
    for raw in blockers or []:
        attacker_id = raw.get("attacker_id")
        blocker_id = raw.get("blocker_id")
        if attacker_id not in attacker_ids or blocker_id not in legal_ids:
            continue
        if blocker_id in used_blockers:
            continue
        # Aerial gating: only aerial / reach defenders can block aerial attackers.
        if not can_block(state.objects.get(blocker_id), state.objects.get(attacker_id)):
            continue
        used_blockers.add(blocker_id)
        block_map[attacker_id] = blocker_id

    return resolve_combat(game, combat.get("attacking_player"), defender_id, attacks, block_map)


def resolve_combat(
    game,
    attacker_player: str,
    defender_id: str,
    attacks: list[dict[str, Any]],
    block_map: dict[str, str],
) -> tuple[bool, str, list[Event]]:
    state = game.state
    events: list[Event] = []
    state.minecraft_combat = {
        "phase": "damage",
        "attacking_player": attacker_player,
        "defending_player": defender_id,
        "attackers": list(attacks),
        "blockers": [{"attacker_id": a, "blocker_id": b} for a, b in block_map.items()],
    }
    attack_event = Event(type=EventType.MC_DECLARE_ATTACKERS, payload=state.minecraft_combat, controller=attacker_player)
    events.append(attack_event)
    block_event = Event(type=EventType.MC_DECLARE_BLOCKERS, payload={"player": defender_id, "blockers": state.minecraft_combat["blockers"]})
    game.emit(block_event)
    events.append(block_event)

    for attack in attacks:
        attacker = state.objects.get(attack["attacker_id"])
        if not attacker or attacker.zone != ZoneType.BATTLEFIELD:
            continue
        attacker_power = _mob_attack_power(attacker, state)
        keywords = mc_keywords_of(attacker)
        blocker = state.objects.get(block_map.get(attacker.id, ""))
        if blocker and blocker.zone == ZoneType.BATTLEFIELD:
            blocker.state.blocking = True
            blocker.state.mc_last_blocked_attacker = attacker.id
            on_block = getattr(blocker.card_def, "mc_on_block", None) if blocker.card_def else None
            if callable(on_block):
                for ev in on_block(blocker, state, attacker.id) or []:
                    game.emit(ev)
                    events.append(ev)
            # Overflow rule: damage to blocker is capped at its remaining HP;
            # any surplus carries through to the column target / avatar.
            blocker_hp = max(0, int(get_toughness(blocker, state) or 0) - int(blocker.state.damage or 0))
            to_blocker = min(attacker_power, blocker_hp) if blocker_hp > 0 else attacker_power
            overflow = max(0, attacker_power - to_blocker)
            damage_to_blocker = Event(type=EventType.DAMAGE, payload={"target": blocker.id, "amount": to_blocker, "source": attacker.id, "is_combat": True}, source=attacker.id)
            game.emit(damage_to_blocker)
            events.append(damage_to_blocker)
            if overflow > 0:
                stored_column = attack.get("target_column")
                column = stored_column if isinstance(stored_column, int) else None
                _, overflow_target = _resolve_attack_target(state, defender_id, attacker, column)
                overflow_event = Event(type=EventType.DAMAGE, payload={"target": overflow_target, "amount": overflow, "source": attacker.id, "is_combat": True, "overflow": True}, source=attacker.id)
                game.emit(overflow_event)
                events.append(overflow_event)
                _apply_infect(state, attacker, overflow_target, overflow, defender_id)
            if "ranged" not in keywords:
                damage_to_attacker = Event(type=EventType.DAMAGE, payload={"target": attacker.id, "amount": int(get_power(blocker, state) or 0), "source": blocker.id, "is_combat": True}, source=blocker.id)
                game.emit(damage_to_attacker)
                events.append(damage_to_attacker)
        else:
            # Re-resolve target at damage time so a destroyed block in this same
            # combat step lets the next attacker punch through.
            stored_column = attack.get("target_column")
            column = stored_column if isinstance(stored_column, int) else attack.get("target_column")
            _, target_id = _resolve_attack_target(state, defender_id, attacker, column)
            damage = Event(type=EventType.DAMAGE, payload={"target": target_id, "amount": attacker_power, "source": attacker.id, "is_combat": True}, source=attacker.id)
            game.emit(damage)
            events.append(damage)
            _apply_infect(state, attacker, target_id, attacker_power, defender_id)
            # Siege: after dealing damage to a Block frontmost, also destroy it.
            if "siege" in keywords and isinstance(column, int):
                front_oid = column_target(state, defender_id, column, keywords)
                front_obj = state.objects.get(front_oid) if front_oid else None
                if front_obj and CardType.MC_BLOCK in front_obj.characteristics.types:
                    destroy = Event(
                        type=EventType.OBJECT_DESTROYED,
                        payload={"object_id": front_obj.id, "reason": "siege"},
                        source=attacker.id,
                    )
                    game.emit(destroy)
                    events.append(destroy)

    marker = Event(type=EventType.MC_COMBAT_DAMAGE, payload={"attacks": attacks, "blockers": state.minecraft_combat["blockers"]})
    game.emit(marker)
    events.append(marker)
    game.check_state_based_actions()
    events.extend(handle_avatar_deaths(game))
    cleanup_references(state)
    for attack in attacks:
        obj = state.objects.get(attack["attacker_id"])
        if obj:
            obj.state.attacking = False
    for pair in state.minecraft_combat["blockers"]:
        obj = state.objects.get(pair["blocker_id"])
        if obj:
            obj.state.blocking = False
    state.minecraft_combat["phase"] = "complete"
    return True, "Combat resolved", events


def register_minecraft_system_interceptors(game) -> None:
    def cleanup_filter(event: Event, state: GameState) -> bool:
        return state.game_mode == "minecraft" and event.type in {
            EventType.ZONE_CHANGE,
            EventType.OBJECT_DESTROYED,
            EventType.EXILE,
            EventType.DAMAGE,
            EventType.MC_MATERIAL_GAIN,
            EventType.MC_MATERIAL_SPEND,
            EventType.MC_PLAY_CARD,
        }

    def _fire_mc_on_event(state: GameState, event: Event) -> None:
        """Generic listener hook: any battlefield card with `mc_on_event`
        receives every MC pipeline event we filter on."""
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return
        g = getattr(state, "_game", None)
        if not g:
            return
        for oid in list(battlefield.objects):
            obj = state.objects.get(oid)
            if not obj or not obj.card_def or obj.zone != ZoneType.BATTLEFIELD:
                continue
            hook = getattr(obj.card_def, "mc_on_event", None)
            if not callable(hook):
                continue
            try:
                emitted = hook(obj, state, event) or []
            except Exception:
                emitted = []
            for ev in emitted:
                g.emit(ev)

    def cleanup_handler(event: Event, state: GameState) -> InterceptorResult:
        # Deathrattle: fire mc_on_death once when a Minecraft object is destroyed
        # or exiled.
        if event.type in {EventType.OBJECT_DESTROYED, EventType.EXILE}:
            oid = event.payload.get("object_id")
            obj = state.objects.get(oid) if oid else None
            if (
                obj
                and obj.card_def
                and not obj.state.death_triggered
                and (
                    CardType.MC_MOB in obj.characteristics.types
                    or CardType.MC_STRUCTURE in obj.characteristics.types
                    or CardType.MC_BLOCK in obj.characteristics.types
                )
            ):
                hook = getattr(obj.card_def, "mc_on_death", None)
                if callable(hook):
                    obj.state.death_triggered = True
                    g = getattr(state, "_game", None)
                    if g:
                        for ev in hook(obj, state) or []:
                            g.emit(ev)
        # On-damage hook: Phyrexian Negator and friends pay a price for surviving.
        elif event.type == EventType.DAMAGE:
            target_id = event.payload.get("target")
            target = state.objects.get(target_id) if target_id else None
            amount = int(event.payload.get("amount", 0) or 0)
            if (
                target
                and target.card_def
                and amount > 0
                and target.zone == ZoneType.BATTLEFIELD
            ):
                hook = getattr(target.card_def, "mc_on_damage", None)
                if callable(hook):
                    g = getattr(state, "_game", None)
                    if g:
                        for ev in hook(target, state, amount) or []:
                            g.emit(ev)
        # Generic per-event listener for cards that need to react to mining
        # ticks, played cards, blocks getting destroyed, etc.
        _fire_mc_on_event(state, event)
        cleanup_references(state)
        return InterceptorResult(action=InterceptorAction.PASS)

    game.register_interceptor(Interceptor(
        id=new_id(),
        source="MC_SYSTEM",
        controller="SYSTEM",
        priority=InterceptorPriority.REACT,
        filter=cleanup_filter,
        handler=cleanup_handler,
        duration="forever",
    ))


def make_minecraft_token(name: str, controller: str, power: int, toughness: int, subtypes: set[str] | None = None) -> Event:
    return Event(
        type=EventType.CREATE_TOKEN,
        payload={
            "controller": controller,
            "token": {
                "name": name,
                "types": {CardType.MC_MOB},
                "subtypes": subtypes or {"Mob"},
                "power": power,
                "toughness": toughness,
            },
        },
    )
