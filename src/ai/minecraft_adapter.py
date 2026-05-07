"""Heuristic AI for the Minecraft TCG alpha."""

from __future__ import annotations

from typing import Optional

from src.engine.types import CardType, GameState, ZoneType
from src.engine import minecraft as mc


# Score tables for each attack-priority preset. Higher score = column
# more attractive to attack. Used by MinecraftAIAdapter._best_attack_column.
_ATTACK_PRIORITY_TABLES: dict[str, dict[str, int]] = {
    # Default heuristic: Bed > Avatar > Structure > Block.
    "bed_first":       {"bed": 100, "avatar": 8,  "structure": 6,  "block": 2,   "other": 4},
    # Rush face damage — go for avatar before anything else.
    "avatar_first":    {"bed": 50,  "avatar": 100, "structure": 4,  "block": 2,   "other": 4},
    # Disrupt opponent's economy — hit turn-bonus structures first.
    "structure_first": {"bed": 60,  "avatar": 8,  "structure": 100, "block": 2,   "other": 4},
    # Block-cracker (Ravager-style): destroy walls for triggers.
    "block_first":     {"bed": 50,  "avatar": 8,  "structure": 6,  "block": 100, "other": 4},
    # Random column.
    "random":          None,
}


# Bias presets for variant-tournament search. Each preset overrides
# scoring weights or selection behavior in `_choose_card_to_play` /
# `_best_biome_to_mine`. The default ("balanced") preset matches the
# meta-aware tuning shipped in `ac9e702`.
#
# Use case: "I don't know what wins yet — let me run a variant
# tournament to find out." Pass `bias=PRESET` (one of the keys below) at
# adapter construction time, or build your own dict.
# Default bias values. Other presets override fields they care about
# and inherit the rest. Avoids duplicating defaults across every preset.
_DEFAULTS = {
    # Card picking
    "selection_mode": "weighted",        # weighted | random | largest
    "worker_bonus_under_3": 25,
    "worker_bonus_first": 15,
    "turnbonus_struct_bonus": 18,
    "explore_map_bonus": 45,
    "strip_mine_bonus": 28,
    "find_diamonds_bonus": 22,
    "chop_trees_bonus": 20,
    "untap_worker_bonus": 15,
    "nether_expedition_bonus": 18,
    "tutor_bonus": 25,
    "draw_bonus": 12,
    "early_big_mob_penalty": 10,
    "late_big_mob_bonus": 10,
    # Penalty applied to a tool/weapon with positive mc_attack when the
    # player has no Bed deployed (suicide-equip avoidance). 0 = no
    # effect for existing presets.
    "weapon_no_bed_penalty": 0,
    # Bonus added to tutor/draw cards (Eyes of Ender, Villager Trade)
    # when the player has no Bed yet, on top of the base tutor/draw
    # bonus. Compensates for Bed copies sitting in the library. 0 = no
    # effect for existing presets.
    "bed_search_bonus": 0,
    # Mining
    # mining_mode: "premium_first" | "wood_first" | "iron_first" |
    # "redstone_first" | "diamond_first" | "random"
    "mining_mode": "premium_first",
    "mine_wood_first_when_pending": True,
    # Combat: attack priority + block mode
    # attack_priority: "bed_first" | "avatar_first" | "structure_first"
    # | "block_first" | "random"
    "attack_priority": "bed_first",
    # block_mode: "auto" (smart engine default) | "never" | "chump_anything"
    "block_mode": "auto",
}


def _preset(**overrides) -> dict:
    out = dict(_DEFAULTS)
    out.update(overrides)
    return out


MC_BIAS_PRESETS: dict[str, dict] = {
    # Default — meta-aware all-axes preset.
    "balanced": _preset(),
    # Single-axis card-picking variants (unchanged behavior on
    # mining/attacks/blocking — those are still the smart defaults).
    "aggro": _preset(
        worker_bonus_under_3=0, worker_bonus_first=0,
        turnbonus_struct_bonus=0, explore_map_bonus=0,
        strip_mine_bonus=0, find_diamonds_bonus=0, chop_trees_bonus=0,
        untap_worker_bonus=0, nether_expedition_bonus=0,
        tutor_bonus=0, draw_bonus=0,
        early_big_mob_penalty=0, late_big_mob_bonus=30,
        mine_wood_first_when_pending=False,
    ),
    "ramp": _preset(
        worker_bonus_under_3=35, worker_bonus_first=25,
        turnbonus_struct_bonus=35, explore_map_bonus=60,
        strip_mine_bonus=40, find_diamonds_bonus=30, chop_trees_bonus=25,
        untap_worker_bonus=20, nether_expedition_bonus=30,
        early_big_mob_penalty=25, late_big_mob_bonus=15,
    ),
    "explore": _preset(
        worker_bonus_under_3=10, worker_bonus_first=10,
        turnbonus_struct_bonus=10, explore_map_bonus=80,
        strip_mine_bonus=10, find_diamonds_bonus=10, chop_trees_bonus=30,
        untap_worker_bonus=5, nether_expedition_bonus=10,
        tutor_bonus=10, draw_bonus=5,
        early_big_mob_penalty=15, late_big_mob_bonus=5,
    ),
    "workers": _preset(
        worker_bonus_under_3=60, worker_bonus_first=30,
        turnbonus_struct_bonus=5, explore_map_bonus=15,
        strip_mine_bonus=15, find_diamonds_bonus=10, chop_trees_bonus=25,
        untap_worker_bonus=30, nether_expedition_bonus=10,
        tutor_bonus=10, draw_bonus=8,
        early_big_mob_penalty=20, late_big_mob_bonus=5,
    ),

    # Random / largest baselines.
    "random":       _preset(selection_mode="random"),
    "fully_random": _preset(selection_mode="random", mining_mode="random",
                            attack_priority="random", block_mode="never"),
    "largest":      _preset(selection_mode="largest"),

    # Cross-axis variants — combine card + mining + attack + block to
    # express a complete strategy, not just a card-picking flavor.
    "iron_rush": _preset(
        # Largest mob you can afford, mine iron aggressively, hit avatar.
        selection_mode="largest", mining_mode="iron_first",
        attack_priority="avatar_first", block_mode="never",
    ),
    "avatar_burn": _preset(
        # Aggro card scoring, but fully committed to face damage.
        worker_bonus_under_3=0, worker_bonus_first=0,
        turnbonus_struct_bonus=0, explore_map_bonus=0,
        strip_mine_bonus=0, find_diamonds_bonus=0, chop_trees_bonus=0,
        untap_worker_bonus=0, nether_expedition_bonus=0,
        tutor_bonus=0, draw_bonus=0,
        early_big_mob_penalty=0, late_big_mob_bonus=30,
        mining_mode="iron_first", attack_priority="avatar_first",
        block_mode="never",
    ),
    "wall_grinder": _preset(
        # Ramp + structure-disruption, kill blocks/structures first to
        # disable opponent's economy. Block normally.
        worker_bonus_under_3=35, worker_bonus_first=25,
        turnbonus_struct_bonus=35, explore_map_bonus=60,
        strip_mine_bonus=40, find_diamonds_bonus=30, chop_trees_bonus=25,
        untap_worker_bonus=20, nether_expedition_bonus=30,
        early_big_mob_penalty=25, late_big_mob_bonus=15,
        attack_priority="block_first",
    ),
    "passive_econ": _preset(
        # Workers tribal + chump-block everything to slow opponent down,
        # then close late.
        # 2026-05-06 (v2): worker_bonus_under_3 60->80 so Workers
        # consistently outscore 4/4 Endermen in early turns;
        # weapon_no_bed_penalty=18 to stop the AI from equipping Iron
        # Sword while undefended; bed_search_bonus=40 to bias tutor /
        # draw effects toward finding the missing Bed.
        # 2026-05-06 (v3): iter-2 found two regressions/undersizes from v2:
        # (1) weapon_no_bed_penalty=18 was numerically too small — Iron
        # Sword (15 + mc_attack=4 = 19) survived the penalty at net +1
        # and was still equipped. Bumped to 28 → net -9, suppressed.
        # (2) Worker-less openings became hyper-passive: with the +80
        # Worker bonus only firing when a Worker is in hand, a Worker-
        # less hand has no high-scoring play, and -20 on big mobs made
        # the AI hold its hand for entire games (iter-2 AI played zero
        # mobs in 8 turns). Lowered early_big_mob_penalty 20 -> 10 in
        # this preset only, so the AI falls back to deploying SOMETHING
        # when no Worker is drawable.
        worker_bonus_under_3=80, worker_bonus_first=30,
        turnbonus_struct_bonus=5, explore_map_bonus=15,
        strip_mine_bonus=15, find_diamonds_bonus=10, chop_trees_bonus=25,
        untap_worker_bonus=30, nether_expedition_bonus=10,
        early_big_mob_penalty=10, late_big_mob_bonus=5,
        weapon_no_bed_penalty=28, bed_search_bonus=40,
        attack_priority="structure_first", block_mode="chump_anything",
    ),
    "wood_economy": _preset(
        # Wood-mining heavy; explore + ramp via wood. Defensive.
        worker_bonus_under_3=40, worker_bonus_first=20,
        turnbonus_struct_bonus=20, explore_map_bonus=70,
        chop_trees_bonus=35, find_diamonds_bonus=10,
        early_big_mob_penalty=15, late_big_mob_bonus=8,
        mining_mode="wood_first", attack_priority="bed_first",
    ),
}


class MinecraftAIAdapter:
    def __init__(self, difficulty: str = "medium", bias: dict | str | None = None):
        """
        bias: either a preset name (key in MC_BIAS_PRESETS) or a dict
              that overrides individual weights. Defaults to "balanced".
        """
        self.difficulty = difficulty
        if bias is None:
            bias = "balanced"
        if isinstance(bias, str):
            preset = MC_BIAS_PRESETS.get(bias)
            if preset is None:
                raise ValueError(f"Unknown MC bias preset: {bias!r}")
            bias_dict = dict(preset)
        else:
            bias_dict = dict(MC_BIAS_PRESETS["balanced"])
            bias_dict.update(bias)
        self.bias = bias_dict

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
            column = self._best_attack_column(state, opponent, kws)
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
                column = self._best_attack_column(state, opponent, kws)
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

        if self.bias.get("mining_mode") == "random":
            import random as _random
            unmined = [i for i, b in enumerate(biomes) if not b.get("mined")]
            return _random.choice(unmined) if unmined else 0

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

        # If we need wood and don't have any, prefer the wood biome —
        # gated on the bias preset so aggro / largest variants ignore
        # the meta and just mine for raw value.
        if wants_wood and my_wood < 2 and self.bias.get("mine_wood_first_when_pending", True):
            for i, biome in enumerate(biomes):
                if biome.get("mined"):
                    continue
                yields = biome.get("yields") or {}
                if int(yields.get("wood", 0) or 0) > 0:
                    return i

        # Mining mode determines material priority order. premium_first is
        # the default heuristic; the others express specific strategic
        # commitments (e.g. iron_rush wants iron above everything).
        priority_orders = {
            "premium_first":  ("diamond", "redstone", "iron", "stone", "wood"),
            "wood_first":     ("wood", "diamond", "redstone", "iron", "stone"),
            "iron_first":     ("iron", "stone", "diamond", "redstone", "wood"),
            "redstone_first": ("redstone", "iron", "stone", "diamond", "wood"),
            "diamond_first":  ("diamond", "redstone", "iron", "stone", "wood"),
        }
        order = priority_orders.get(self.bias.get("mining_mode", "premium_first"),
                                    priority_orders["premium_first"])
        for material in order:
            for i, biome in enumerate(biomes):
                if not biome.get("mined") and int((biome.get("yields") or {}).get(material, 0) or 0) > 0:
                    return i
        return 0

    def _best_attack_column(
        self, state: GameState, defender_id: str, attacker_keywords: set[str]
    ) -> int:
        """Pick attack column based on `bias['attack_priority']`.

        Default ('bed_first') matches the original heuristic. Other modes
        rank columns by what's frontmost (avatar / structure / block /
        bed / other) using the per-mode score table in
        _ATTACK_PRIORITY_TABLES. Random mode picks any column.
        """
        priority = self.bias.get("attack_priority", "bed_first")
        if priority == "random":
            import random as _random
            return _random.randrange(mc.GRID_SIZE)
        table = _ATTACK_PRIORITY_TABLES.get(priority) or _ATTACK_PRIORITY_TABLES["bed_first"]

        best_score = -1
        best_col = 0
        for column in range(mc.GRID_SIZE):
            oid = mc.column_target(state, defender_id, column, attacker_keywords)
            if not oid:
                score = table["avatar"]
            else:
                obj = state.objects.get(oid)
                if not obj:
                    score = 0
                elif "Bed" in obj.characteristics.subtypes:
                    score = table["bed"]
                elif CardType.MC_BLOCK in obj.characteristics.types:
                    score = table["block"]
                elif CardType.MC_STRUCTURE in obj.characteristics.types:
                    score = table["structure"]
                else:
                    score = table["other"]
            if score > best_score:
                best_score = score
                best_col = column
        return best_col

    def choose_blockers(
        self, state: GameState, defender_id: str, attackers: list[dict]
    ) -> dict[str, str]:
        """
        Return {attacker_id: blocker_id} for AI defenders. Default mode
        ('auto') delegates to mc.auto_blockers (the smart heuristic).
        """
        mode = self.bias.get("block_mode", "auto")
        if mode == "never":
            return {}
        if mode == "chump_anything":
            # Pair every attacker with any unused legal blocker, even bad
            # trades. Models the "stall everything" archetype.
            from src.engine.minecraft import legal_blockers
            block_map: dict[str, str] = {}
            available = list(legal_blockers(state, defender_id))
            for atk in attackers:
                if not available:
                    break
                aid = atk.get("attacker_id")
                if not aid:
                    continue
                block_map[aid] = available.pop(0)
            return block_map
        # Default — engine-supplied smart blocker logic.
        return mc.auto_blockers(state, defender_id, attackers)

    def _choose_card_to_play(self, state: GameState, player_id: str) -> Optional[str]:
        """
        Phase-aware card scoring driven by self.bias presets.
        """
        hand = state.zones.get(f"hand_{player_id}")
        if not hand:
            return None

        bias = self.bias
        mode = bias.get("selection_mode", "weighted")

        # Build the affordable-card pool (used by all selection modes).
        affordable: list[tuple[str, GameObject]] = []
        for oid in hand.objects:
            obj = state.objects.get(oid)
            if not obj or not obj.card_def:
                continue
            cost = mc._discounted_cost(state, player_id, obj)
            if mc.can_pay(state, player_id, cost):
                affordable.append((oid, obj))
        if not affordable:
            return None

        if mode == "random":
            import random as _random
            return _random.choice(affordable)[0]

        if mode == "largest":
            # Pick the highest-cost-total affordable card. Tiebreak on
            # mob power+toughness so 5-cost mobs beat 5-cost actions.
            def _key(item):
                _oid, o = item
                cost = mc._discounted_cost(state, player_id, o)
                cost_total = sum(int(v or 0) for v in (cost or {}).values())
                pt = (o.characteristics.power or 0) + (o.characteristics.toughness or 0)
                return (cost_total, pt)
            affordable.sort(key=_key, reverse=True)
            return affordable[0][0]

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
        for oid, obj in affordable:
            score = 0
            name = obj.name
            types = obj.characteristics.types or set()
            subtypes = obj.characteristics.subtypes or set()
            cost = mc._discounted_cost(state, player_id, obj)
            cost_total = sum(int(v or 0) for v in (cost or {}).values())

            if "Bed" in subtypes and not has_bed:
                score += 100

            if CardType.MC_MOB in types and "Worker" in subtypes:
                score += 20 + (obj.characteristics.power or 0) + (obj.characteristics.toughness or 0)
                if my_workers_count < 3:
                    score += int(bias.get("worker_bonus_under_3", 0))
                if my_workers_count < 1:
                    score += int(bias.get("worker_bonus_first", 0))
            elif CardType.MC_MOB in types:
                score += 20 + (obj.characteristics.power or 0) + (obj.characteristics.toughness or 0)
                if turn_number <= 2 and cost_total >= 5:
                    score -= int(bias.get("early_big_mob_penalty", 0))
                if turn_number >= 6 and cost_total >= 4:
                    score += int(bias.get("late_big_mob_bonus", 0))

            if CardType.MC_STRUCTURE in types or CardType.MC_BLOCK in types:
                if "Bed" not in subtypes:
                    score += 12 + (obj.characteristics.toughness or 0)
                    turn_bonus = getattr(obj.card_def, "mc_turn_bonus", None) or {}
                    if turn_bonus and my_turnbonus_structures < 3:
                        score += int(bias.get("turnbonus_struct_bonus", 0))

            if CardType.MC_TOOL in types:
                score += 15 + int(getattr(obj.card_def, "mc_attack", 0) or 0)
                # Penalize equipping an offensive weapon when undefended:
                # the AI's avatar dying mid-game is far worse than a
                # delayed equip.
                if (
                    not has_bed
                    and int(getattr(obj.card_def, "mc_attack", 0) or 0) > 0
                ):
                    score -= int(bias.get("weapon_no_bed_penalty", 0))

            if CardType.MC_ACTION in types:
                score += 8
                if name == "Explore Map" and any_biome_upgradable:
                    score += int(bias.get("explore_map_bonus", 0))
                if name == "Strip Mine" and int(my_materials.get("redstone", 0) or 0) < 2:
                    score += int(bias.get("strip_mine_bonus", 0))
                if name == "Find Diamonds" and int(my_materials.get("diamond", 0) or 0) < 2:
                    score += int(bias.get("find_diamonds_bonus", 0))
                if name == "Chop Trees" and (turn_number <= 4 or int(my_materials.get("wood", 0) or 0) < 2):
                    score += int(bias.get("chop_trees_bonus", 0))
                if name in ("Bone Meal", "Redstone Contraption") and my_workers_count > 0:
                    score += int(bias.get("untap_worker_bonus", 0))
                if name == "Nether Expedition":
                    score += int(bias.get("nether_expedition_bonus", 0))
                if name == "Eyes of Ender":
                    score += int(bias.get("tutor_bonus", 0))
                    if not has_bed:
                        score += int(bias.get("bed_search_bonus", 0))
                if name == "Villager Trade":
                    score += int(bias.get("draw_bonus", 0))
                    if not has_bed:
                        score += int(bias.get("bed_search_bonus", 0))

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
