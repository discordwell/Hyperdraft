"""Heuristic AI for the Minecraft TCG alpha."""

from __future__ import annotations

from typing import Optional

from src.engine.types import CardType, GameState, ZoneType
from src.engine import minecraft as mc


def _best_attack_column(state: GameState, defender_id: str, attacker_keywords: set[str]) -> int:
    """Pick the most valuable column to attack: bed > big structure > empty (avatar) > anything."""
    best_score = -1
    best_col = 0
    for column in range(mc.GRID_SIZE):
        oid = mc.column_target(state, defender_id, column, attacker_keywords)
        if not oid:
            score = 8  # column clear → hits avatar (very valuable)
        else:
            obj = state.objects.get(oid)
            if not obj:
                score = 0
            elif "Bed" in obj.characteristics.subtypes:
                score = 100
            elif CardType.MC_BLOCK in obj.characteristics.types:
                score = 2  # break through walls slowly
            elif CardType.MC_STRUCTURE in obj.characteristics.types:
                score = 6
            else:
                score = 4
        if score > best_score:
            best_score = score
            best_col = column
    return best_col


class MinecraftAIAdapter:
    def __init__(self, difficulty: str = "medium"):
        self.difficulty = difficulty

    async def take_turn(self, player_id: str, state: GameState, game) -> list:
        events = []
        if not game:
            return events
        mc.ensure_player_state(state, player_id)

        opponent = self._opponent_id(state, player_id)
        player = state.players[player_id]
        weapon_id = player.mc_avatar_gear.get("weapon")

        # Avatar action: attack with weapon if equipped, otherwise mine.
        if not player.mc_avatar_action_used and weapon_id and opponent:
            weapon = state.objects.get(weapon_id)
            kws: set[str] = set()
            if weapon and weapon.card_def:
                kws = {str(k).lower() for k in (getattr(weapon.card_def, "mc_keywords", None) or ())}
            column = _best_attack_column(state, opponent, kws)
            ok, _msg, evs = mc.avatar_attack(game, player_id, target_column=column)
            if ok:
                events.extend(evs)
        elif not player.mc_avatar_action_used:
            idx = self._best_biome_to_mine(state, player_id)
            ok, _msg, evs = mc.mine_biome(game, player_id, idx, avatar=True)
            if ok:
                events.extend(evs)

        events.extend(self._play_affordable_cards(state, player_id, game))
        if game.is_game_over():
            return events

        opponent = self._opponent_id(state, player_id)
        attacks: list[dict] = []
        if opponent:
            for attacker_id in self._available_attackers(state, player_id):
                attacker = state.objects.get(attacker_id)
                kws = mc.mc_keywords_of(attacker)
                column = _best_attack_column(state, opponent, kws)
                attacks.append({"attacker_id": attacker_id, "target_column": column})
        if attacks:
            human_players = set(state.turn_data.get("mc_human_players") or [])
            ok, _msg, evs = mc.declare_attackers(
                game,
                player_id,
                attacks,
                auto_block=opponent not in human_players,
            )
            if ok:
                events.extend(evs)
                game.check_state_based_actions()
                events.extend(mc.handle_avatar_deaths(game))
                if game.is_game_over():
                    return events

        # Mine after combat so hostiles do not spend themselves instead of
        # attacking. Each biome slot still caps mining to once per turn.
        for worker_id in self._available_workers(state, player_id):
            idx = self._best_biome_to_mine(state, player_id)
            ok, _msg, evs = mc.mine_biome(game, player_id, idx, actor_id=worker_id)
            if ok:
                events.extend(evs)

        events.extend(self._play_affordable_cards(state, player_id, game))

        return events

    def _play_affordable_cards(self, state: GameState, player_id: str, game) -> list:
        events = []
        target = self._preferred_target(state, self._opponent_id(state, player_id))
        for _ in range(12):
            card_id = self._choose_card_to_play(state, player_id)
            if not card_id:
                break
            cell = self._choose_cell_for_card(state, player_id, card_id)
            ok, _msg, evs = mc.play_card(game, player_id, card_id, cell=cell, target_id=target)
            if not ok:
                break
            events.extend(evs)
            game.check_state_based_actions()
            events.extend(mc.handle_avatar_deaths(game))
            if game.is_game_over():
                break
        return events

    def _ready_mobs(self, state: GameState, player_id: str) -> list:
        battlefield = state.zones.get("battlefield")
        if not battlefield:
            return []
        out = []
        for oid in battlefield.objects:
            obj = state.objects.get(oid)
            if (
                obj
                and obj.controller == player_id
                and obj.zone == ZoneType.BATTLEFIELD
                and CardType.MC_MOB in obj.characteristics.types
                and not obj.state.tapped
                and not obj.state.mc_exhausted
                and not obj.state.summoning_sickness
            ):
                out.append(obj)
        return out

    def _available_attackers(self, state: GameState, player_id: str) -> list[str]:
        return [obj.id for obj in self._ready_mobs(state, player_id) if "Worker" not in obj.characteristics.subtypes]

    def _available_workers(self, state: GameState, player_id: str) -> list[str]:
        return [obj.id for obj in self._ready_mobs(state, player_id) if "Worker" in obj.characteristics.subtypes]

    def _opponent_id(self, state: GameState, player_id: str) -> Optional[str]:
        return next((pid for pid in state.players if pid != player_id and not state.players[pid].has_lost), None)

    def _preferred_target(self, state: GameState, opponent_id: Optional[str]) -> Optional[str]:
        if not opponent_id:
            return None
        targets = mc.exposed_grid_targets(state, opponent_id)
        bed = next((tid for tid in targets if "Bed" in state.objects[tid].characteristics.subtypes), None)
        return bed or (targets[0] if targets else opponent_id)

    def _best_biome_to_mine(self, state: GameState, player_id: str) -> int:
        """
        Pick the most valuable biome to mine this turn.

        Default priority is premium materials (diamond > redstone > iron >
        stone > wood). But if we *need* wood now — to play a Worker or
        Explore Map sitting in hand, or because we have no other wood
        income — bias toward the wood biome instead. Wood's leverage
        early is highest in the format (Explore Map = 1W for permanent
        +1 yield; Workers cost 1W each).
        """
        biomes = state.minecraft_biomes.get(player_id) or []
        if not biomes:
            return 0

        player = state.players.get(player_id)
        my_wood = int((player.mc_materials if player else {}).get("wood", 0) or 0)

        # Inspect hand for cards that need wood urgently.
        hand = state.zones.get(f"hand_{player_id}")
        wants_wood = False
        if hand:
            for oid in hand.objects:
                obj = state.objects.get(oid)
                if not obj or not obj.card_def:
                    continue
                cost = mc._discounted_cost(state, player_id, obj)
                wood_cost = int((cost or {}).get("wood", 0) or 0)
                if wood_cost <= 0:
                    continue
                # Explore Map (the 1 wood) — top of the meta priority list.
                if obj.name == "Explore Map":
                    wants_wood = True
                    break
                # Workers cost wood and they compound — prefer mining wood
                # for them too, especially when we don't have any yet.
                if (
                    CardType.MC_MOB in obj.characteristics.types
                    and "Worker" in (obj.characteristics.subtypes or set())
                ):
                    wants_wood = True
                    break
                # Bed is fundamental and costs 2 wood.
                if "Bed" in obj.characteristics.subtypes and not mc.has_bed(state, player_id):
                    wants_wood = True
                    break

        # If we need wood and don't have any, prefer the wood biome.
        if wants_wood and my_wood < 2:
            for i, biome in enumerate(biomes):
                if biome.get("mined"):
                    continue
                yields = biome.get("yields") or {}
                if int(yields.get("wood", 0) or 0) > 0:
                    return i

        # Otherwise: premium-material priority (diamond > redstone > iron > stone > wood).
        for material in ("diamond", "redstone", "iron", "stone", "wood"):
            for i, biome in enumerate(biomes):
                if not biome.get("mined") and int((biome.get("yields") or {}).get(material, 0) or 0) > 0:
                    return i
        return 0

    def _choose_card_to_play(self, state: GameState, player_id: str) -> Optional[str]:
        """
        Phase-aware card scoring that follows the MC meta:
          1. Explore biomes (1 wood -> permanent +1 yield)
          2. Deploy Workers ASAP (compounding economy)
          3. Upgrade material generation (turn-bonus structures)
          4. Then deploy big mobs / tempo plays

        Scoring is baseline + per-card meta bumps. Action cards used to
        score 8 (worst) which made the AI ignore Strip Mine, Explore Map,
        Find Diamonds — the entire ramp toolkit.
        """
        hand = state.zones.get(f"hand_{player_id}")
        if not hand:
            return None

        # Read game state needed for phase-aware scoring.
        turn_number = int(getattr(state, "turn_number", 0) or 0)
        biomes = state.minecraft_biomes.get(player_id) or []
        any_biome_upgradable = any(
            mc.BIOME_UPGRADES.get((b or {}).get("name")) for b in biomes
        )
        battlefield = state.zones.get("battlefield")
        my_workers_count = 0
        my_turnbonus_structures = 0
        if battlefield:
            for oid_bf in battlefield.objects:
                o = state.objects.get(oid_bf)
                if not o or o.controller != player_id or not o.card_def:
                    continue
                if CardType.MC_MOB in o.characteristics.types and "Worker" in o.characteristics.subtypes:
                    my_workers_count += 1
                if CardType.MC_STRUCTURE in o.characteristics.types:
                    if (getattr(o.card_def, "mc_turn_bonus", None) or {}):
                        my_turnbonus_structures += 1

        player = state.players.get(player_id)
        my_materials = (player.mc_materials if player else {}) or {}

        candidates = []
        has_bed = mc.has_bed(state, player_id)
        for oid in hand.objects:
            obj = state.objects.get(oid)
            if not obj or not obj.card_def:
                continue
            cost = mc._discounted_cost(state, player_id, obj)
            if not mc.can_pay(state, player_id, cost):
                continue

            score = 0
            name = obj.name
            types = obj.characteristics.types or set()
            subtypes = obj.characteristics.subtypes or set()
            cost_total = sum(int(v or 0) for v in (cost or {}).values())

            # Bed first — fundamental respawn lifeline.
            if "Bed" in subtypes and not has_bed:
                score += 100

            # Workers — deploy ASAP. Diminishing returns past 3.
            if CardType.MC_MOB in types and "Worker" in subtypes:
                # Base mob value
                score += 20 + (obj.characteristics.power or 0) + (obj.characteristics.toughness or 0)
                # Worker meta bonus
                if my_workers_count < 3:
                    score += 25
                if my_workers_count < 1:
                    score += 15  # extra-urgent for the first one

            # Non-Worker Mob
            elif CardType.MC_MOB in types:
                score += 20 + (obj.characteristics.power or 0) + (obj.characteristics.toughness or 0)
                # Penalize the *biggest* mobs early — we should be ramping,
                # not slamming. Threshold raised to 5 so 3-mana mid mobs
                # (Iron Golem, Ravager, Blaze) aren't suppressed.
                if turn_number <= 2 and cost_total >= 5:
                    score -= 10
                # Bonus for big mobs late (we're ready to close).
                if turn_number >= 6 and cost_total >= 4:
                    score += 10

            # Structures: turn-bonus = ramp engine, prioritize early.
            if CardType.MC_STRUCTURE in types or CardType.MC_BLOCK in types:
                if "Bed" in subtypes:
                    pass  # handled above
                else:
                    score += 12 + (obj.characteristics.toughness or 0)
                    turn_bonus = getattr(obj.card_def, "mc_turn_bonus", None) or {}
                    if turn_bonus and my_turnbonus_structures < 3:
                        score += 18  # ramp structure — high priority

            if CardType.MC_TOOL in types:
                score += 15 + int(getattr(obj.card_def, "mc_attack", 0) or 0)

            # Actions — used to be flat 8. Now meta-aware.
            if CardType.MC_ACTION in types:
                score += 8
                # Explore Map: 1 wood for permanent biome upgrade. Best card
                # in the format if any biome can still be upgraded.
                if name == "Explore Map" and any_biome_upgradable:
                    score += 45
                # Strip Mine: only cheap entry to redstone.
                if name == "Strip Mine":
                    if int(my_materials.get("redstone", 0) or 0) < 2:
                        score += 28
                # Find Diamonds: only entry to diamond.
                if name == "Find Diamonds":
                    if int(my_materials.get("diamond", 0) or 0) < 2:
                        score += 22
                # Chop Trees: free wood, always good early.
                if name == "Chop Trees":
                    if turn_number <= 4 or int(my_materials.get("wood", 0) or 0) < 2:
                        score += 20
                # Bone Meal / Redstone Contraption: untap workers, only
                # valuable if we actually have tapped workers.
                if name in ("Bone Meal", "Redstone Contraption"):
                    if my_workers_count > 0:
                        score += 15
                # Nether Expedition: ramp + draw.
                if name == "Nether Expedition":
                    score += 18
                # Eyes of Ender: tutor.
                if name == "Eyes of Ender":
                    score += 25
                # Villager Trade: card draw.
                if name == "Villager Trade":
                    score += 12

            candidates.append((score, oid))

        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _choose_cell_for_card(self, state: GameState, player_id: str, card_id: str):
        obj = state.objects.get(card_id)
        if not obj:
            return None
        if not (CardType.MC_STRUCTURE in obj.characteristics.types or CardType.MC_BLOCK in obj.characteristics.types):
            return None
        grid = state.minecraft_grid.get(player_id) or mc.empty_grid()
        # 3x3 grid: y=0 is back row, y=2 is front row.
        if "Bed" in obj.characteristics.subtypes:
            preferred = [(1, 0), (0, 0), (2, 0)]
        elif CardType.MC_BLOCK in obj.characteristics.types:
            preferred = [(1, 2), (0, 2), (2, 2), (1, 1), (0, 1), (2, 1)]
        else:
            preferred = [(1, 1), (0, 1), (2, 1), (1, 0), (0, 0), (2, 0)]
        for x, y in preferred:
            if grid[y][x] is None:
                return {"x": x, "y": y}
        for y in range(mc.GRID_SIZE):
            for x in range(mc.GRID_SIZE):
                if grid[y][x] is None:
                    return {"x": x, "y": y}
        return None
