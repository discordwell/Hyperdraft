import asyncio

from fastapi import BackgroundTasks

from src.engine.game import Game
from src.engine.types import CardType, Event, EventType, ZoneType
from src.engine import minecraft as mc
from src.ai.minecraft_adapter import MinecraftAIAdapter
from src.cards.minecraft import MINECRAFT_CARDS
from src.server.models import CreateMatchRequest
from src.server.routes.match import create_match
from src.server.session import session_manager


def _hand_card(game, player_id, card_def):
    return game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_minecraft_play_card_pays_materials_and_places_bed_on_grid():
    game = Game(mode="minecraft")
    p1 = game.add_player("Builder")
    p2 = game.add_player("Raider")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials["wood"] = 3

    bed = _hand_card(game, p1.id, MINECRAFT_CARDS["Bed"])
    ok, message, _events = mc.play_card(game, p1.id, bed.id, cell={"x": 1, "y": 0})

    assert ok, message
    # Day grants the first Structure/Block craft a 1 Wood/Stone discount.
    assert p1.mc_materials["wood"] == 2
    assert game.state.minecraft_grid[p1.id][0][1] == bed.id
    assert bed.zone == ZoneType.BATTLEFIELD
    assert "Bed" in bed.characteristics.subtypes


def test_minecraft_bed_respawns_avatar_and_discards_gear():
    game = Game(mode="minecraft")
    p1 = game.add_player("Builder")
    p2 = game.add_player("Raider")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"wood": 5, "iron": 5})

    bed = _hand_card(game, p1.id, MINECRAFT_CARDS["Bed"])
    sword = _hand_card(game, p1.id, MINECRAFT_CARDS["Iron Sword"])
    assert mc.play_card(game, p1.id, bed.id, cell={"x": 1, "y": 0})[0]
    assert mc.play_card(game, p1.id, sword.id)[0]
    assert p1.mc_avatar_gear["weapon"] == sword.id

    game.emit(Event(type=EventType.DAMAGE, payload={"target": p1.id, "amount": 99}))
    game.check_state_based_actions()

    assert p1.life == 20
    assert not p1.has_lost
    assert p1.mc_avatar_gear["weapon"] is None
    assert sword.zone == ZoneType.GRAVEYARD


def test_minecraft_avatar_without_bed_loses_on_lethal_damage():
    game = Game(mode="minecraft")
    p1 = game.add_player("No Bed")
    p2 = game.add_player("Attacker")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    game.emit(Event(type=EventType.DAMAGE, payload={"target": p1.id, "amount": 20}))
    game.check_state_based_actions()

    assert p1.has_lost


def test_minecraft_column_target_picks_frontmost():
    game = Game(mode="minecraft")
    p1 = game.add_player("Defender")
    p2 = game.add_player("Attacker")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"wood": 10, "stone": 10})

    bed = _hand_card(game, p1.id, MINECRAFT_CARDS["Bed"])
    assert mc.play_card(game, p1.id, bed.id, cell={"x": 1, "y": 0})[0]
    # With nothing in front of the Bed, attacking column 1 hits the Bed.
    assert mc.column_target(game.state, p1.id, 1) == bed.id
    assert mc.is_exposed_grid_object(game.state, bed.id)

    # Place a wall in front of the bed (same column, front row).
    front_wall = _hand_card(game, p1.id, MINECRAFT_CARDS["Cobblestone Wall"])
    assert mc.play_card(game, p1.id, front_wall.id, cell={"x": 1, "y": 2})[0]
    # Now column 1 hits the wall, not the bed.
    assert mc.column_target(game.state, p1.id, 1) == front_wall.id
    assert not mc.is_exposed_grid_object(game.state, bed.id)
    # Empty columns return None (avatar takes the hit).
    assert mc.column_target(game.state, p1.id, 0) is None
    assert mc.column_target(game.state, p1.id, 2) is None


def test_minecraft_turn_ready_clears_mob_summoning_sickness():
    game = Game(mode="minecraft")
    p1 = game.add_player("Builder")
    p2 = game.add_player("Raider")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    helper = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    helper.controller = p1.id
    helper.state.summoning_sickness = True
    helper.state.tapped = True
    helper.state.mc_exhausted = True

    mc.reset_for_turn(game.state, p1.id)

    assert helper.state.summoning_sickness is False
    assert helper.state.tapped is False
    assert helper.state.mc_exhausted is False


def test_minecraft_structure_start_turn_bonus_generates_materials():
    game = Game(mode="minecraft")
    p1 = game.add_player("Builder")
    p2 = game.add_player("Raider")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    furnace = game.create_object(
        name=MINECRAFT_CARDS["Furnace"].name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Furnace"].characteristics,
        card_def=MINECRAFT_CARDS["Furnace"],
    )
    furnace.controller = p1.id

    events = mc.apply_start_turn_bonuses(game, p1.id)

    assert p1.mc_materials["iron"] == 1
    assert any(event.type == EventType.MC_MATERIAL_GAIN for event in events)


def test_minecraft_workers_can_mine_each_unmined_biome_once():
    game = Game(mode="minecraft")
    p1 = game.add_player("Builder")
    p2 = game.add_player("Raider")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    zombie = game.create_object(
        name=MINECRAFT_CARDS["Zombie"].name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Zombie"].characteristics,
        card_def=MINECRAFT_CARDS["Zombie"],
    )
    zombie.controller = p1.id
    zombie.state.summoning_sickness = False
    helper = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    helper.controller = p1.id
    helper.state.summoning_sickness = False
    scout = game.create_object(
        name=MINECRAFT_CARDS["Alex's Scout"].name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Alex's Scout"].characteristics,
        card_def=MINECRAFT_CARDS["Alex's Scout"],
    )
    scout.controller = p1.id
    scout.state.summoning_sickness = False

    ok, message, _events = mc.mine_biome(game, p1.id, 0, actor_id=zombie.id)
    assert not ok
    assert message == "Only Worker mobs can mine"

    ok, message, _events = mc.mine_biome(game, p1.id, 0, avatar=True)
    assert ok, message
    assert p1.mc_avatar_action_used is True

    ok, message, _events = mc.mine_biome(game, p1.id, 0, actor_id=helper.id)
    assert not ok
    assert message == "Biome already mined this turn"

    ok, message, _events = mc.mine_biome(game, p1.id, 1, actor_id=helper.id)
    assert ok, message

    ok, message, _events = mc.mine_biome(game, p1.id, 2, actor_id=scout.id)
    assert ok, message
    assert helper.state.mc_exhausted is True
    assert scout.state.mc_exhausted is True


def test_minecraft_manual_block_declaration_resolves_combat():
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id

    attacker = game.create_object(
        name=MINECRAFT_CARDS["Wolf Pack"].name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Wolf Pack"].characteristics,
        card_def=MINECRAFT_CARDS["Wolf Pack"],
    )
    attacker.controller = p1.id
    attacker.state.summoning_sickness = False
    defender = game.create_object(
        name=MINECRAFT_CARDS["Snow Golem"].name,
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Snow Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Snow Golem"],
    )
    defender.controller = p2.id

    ok, message, _events = mc.declare_attackers(
        game,
        p1.id,
        [{"attacker_id": attacker.id, "target_id": p2.id}],
        auto_block=False,
    )
    assert ok, message
    assert game.state.minecraft_combat["phase"] == "declare_blockers"
    assert defender.id in game.state.minecraft_combat["legal_blockers"]

    ok, message, _events = mc.declare_blockers(
        game,
        p2.id,
        [{"attacker_id": attacker.id, "blocker_id": defender.id}],
    )

    assert ok, message
    assert p2.life == 20
    # Wolf Pack (3/2) takes Snow Golem's 1 combat damage + 1 chip from on_block.
    assert attacker.state.damage == 2
    assert defender.state.damage == 3
    assert game.state.minecraft_combat["phase"] == "complete"


def test_minecraft_ai_attacks_with_ready_hostile_instead_of_mining_it():
    async def _run():
        game = Game(mode="minecraft")
        p1 = game.add_player("AI Raider")
        p2 = game.add_player("Human Builder")
        game.setup_minecraft_player(p1, [])
        game.setup_minecraft_player(p2, [])
        game.state.active_player = p1.id

        creeper = game.create_object(
            name=MINECRAFT_CARDS["Creeper"].name,
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=MINECRAFT_CARDS["Creeper"].characteristics,
            card_def=MINECRAFT_CARDS["Creeper"],
        )
        creeper.controller = p1.id
        creeper.state.summoning_sickness = False

        await MinecraftAIAdapter().take_turn(p1.id, game.state, game)

        assert creeper.state.tapped is True
        assert creeper.state.mc_exhausted is True
        assert p2.life == 16
        assert game.state.minecraft_combat["phase"] == "complete"

    asyncio.run(_run())


def test_builder_starter_has_weapons_and_enough_mobs():
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS

    deck = MINECRAFT_STARTER_DECKS["builder"]()
    unique_names = {card.name for card in deck}
    mob_count = sum(1 for name in unique_names if CardType.MC_MOB in MINECRAFT_CARDS[name].characteristics.types)
    weapon_count = sum(
        1
        for name in unique_names
        if CardType.MC_TOOL in MINECRAFT_CARDS[name].characteristics.types
        and getattr(MINECRAFT_CARDS[name], "mc_tool_slot", None) == "weapon"
    )

    assert len(deck) == 50
    assert mob_count >= 8
    assert weapon_count >= 2


def test_raider_starter_has_workers_ramp_and_lower_curve():
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS

    deck = MINECRAFT_STARTER_DECKS["raider"]()
    unique_names = {card.name for card in deck}

    assert len(deck) == 50
    assert {"Steve's Helper", "Alex's Scout", "Strip Mine"}.issubset(unique_names)
    assert "Warden" not in unique_names
    assert "Wither" in unique_names


def test_minecraft_column_attack_hits_wall_protecting_bed():
    """A wall in the same column as the Bed soaks the attack."""
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.mc_materials.update({"wood": 5, "stone": 5})

    bed = _hand_card(game, p2.id, MINECRAFT_CARDS["Bed"])
    wall = _hand_card(game, p2.id, MINECRAFT_CARDS["Cobblestone Wall"])
    assert mc.play_card(game, p2.id, bed.id, cell={"x": 1, "y": 0})[0]
    assert mc.play_card(game, p2.id, wall.id, cell={"x": 1, "y": 2})[0]

    creeper = game.create_object(
        name=MINECRAFT_CARDS["Creeper"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Creeper"].characteristics,
        card_def=MINECRAFT_CARDS["Creeper"],
    )
    creeper.controller = p1.id
    creeper.state.summoning_sickness = False

    ok, msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": creeper.id, "target_column": 1}],
        auto_block=True,
    )
    assert ok, msg
    # Wall (HP 6) takes 4 damage from Creeper; bed untouched.
    assert wall.state.damage == 4
    assert bed.state.damage == 0


def test_minecraft_aerial_keyword_skips_blocks():
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.mc_materials.update({"wood": 5, "stone": 5})

    bed = _hand_card(game, p2.id, MINECRAFT_CARDS["Bed"])
    wall = _hand_card(game, p2.id, MINECRAFT_CARDS["Cobblestone Wall"])
    assert mc.play_card(game, p2.id, bed.id, cell={"x": 1, "y": 0})[0]
    assert mc.play_card(game, p2.id, wall.id, cell={"x": 1, "y": 2})[0]

    ghast = game.create_object(
        name=MINECRAFT_CARDS["Ghast"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Ghast"].characteristics,
        card_def=MINECRAFT_CARDS["Ghast"],
    )
    ghast.controller = p1.id
    ghast.state.summoning_sickness = False

    ok, msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": ghast.id, "target_column": 1}],
        auto_block=True,
    )
    assert ok, msg
    # Aerial Ghast (5 ATK) skips wall, hits Bed (HP 4) → bed at 5 dmg.
    assert wall.state.damage == 0
    assert bed.state.damage == 5


def test_minecraft_climb_keyword_skips_walls_only():
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.mc_materials.update({"wood": 5, "iron": 5})

    bed = _hand_card(game, p2.id, MINECRAFT_CARDS["Bed"])
    door = _hand_card(game, p2.id, MINECRAFT_CARDS["Iron Door"])  # not subtype Wall
    assert mc.play_card(game, p2.id, bed.id, cell={"x": 0, "y": 0})[0]
    assert mc.play_card(game, p2.id, door.id, cell={"x": 0, "y": 2})[0]

    spider = game.create_object(
        name=MINECRAFT_CARDS["Spider"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Spider"].characteristics,
        card_def=MINECRAFT_CARDS["Spider"],
    )
    spider.controller = p1.id
    spider.state.summoning_sickness = False

    ok, msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": spider.id, "target_column": 0}],
        auto_block=True,
    )
    assert ok, msg
    # Climb only skips Walls; Iron Door is not a Wall subtype.
    assert door.state.damage == 2
    assert bed.state.damage == 0


def test_minecraft_siege_destroys_block_after_damage():
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.mc_materials.update({"stone": 5})

    wall = _hand_card(game, p2.id, MINECRAFT_CARDS["Cobblestone Wall"])
    assert mc.play_card(game, p2.id, wall.id, cell={"x": 0, "y": 2})[0]

    ravager = game.create_object(
        name=MINECRAFT_CARDS["Ravager"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Ravager"].characteristics,
        card_def=MINECRAFT_CARDS["Ravager"],
    )
    ravager.controller = p1.id
    ravager.state.summoning_sickness = False

    ok, msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": ravager.id, "target_column": 0}],
        auto_block=True,
    )
    assert ok, msg
    # Siege destroys the wall outright after dealing damage.
    assert wall.zone == ZoneType.GRAVEYARD


def test_minecraft_ranged_keyword_avoids_blocker_damage():
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id

    archer = game.create_object(
        name=MINECRAFT_CARDS["Skeleton Archer"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Skeleton Archer"].characteristics,
        card_def=MINECRAFT_CARDS["Skeleton Archer"],
    )
    archer.controller = p1.id
    archer.state.summoning_sickness = False
    blocker = game.create_object(
        name=MINECRAFT_CARDS["Wolf Pack"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Wolf Pack"].characteristics,
        card_def=MINECRAFT_CARDS["Wolf Pack"],
    )
    blocker.controller = p2.id

    ok, msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": archer.id, "target_column": 0}],
        auto_block=True,
    )
    assert ok, msg
    # Ranged: archer takes no damage from blocker.
    assert archer.state.damage == 0
    # Wolf Pack (HP 2) takes 2 (capped); overflow 1 goes through to defender avatar.
    # Blocker took 1 chip after Wolf Pack joined (worker bonus on Wolf Pack? no, ATK only)
    assert blocker.state.damage == 2
    assert p2.life == 19


def test_minecraft_pillager_lord_buffs_other_raiders():
    game = Game(mode="minecraft")
    p1 = game.add_player("Raid")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    pillager = game.create_object(
        name=MINECRAFT_CARDS["Pillager Patrol"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Pillager Patrol"].characteristics,
        card_def=MINECRAFT_CARDS["Pillager Patrol"],
    )
    pillager.controller = p1.id
    raider = game.create_object(
        name=MINECRAFT_CARDS["Piglin Raider"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Piglin Raider"].characteristics,
        card_def=MINECRAFT_CARDS["Piglin Raider"],
    )
    raider.controller = p1.id

    # Piglin Raider is base 3/2, gains +1 from Pillager lord.
    assert mc._mob_attack_power(raider, game.state) == 4
    # Pillager itself is unaffected (no self-buff).
    assert mc._mob_attack_power(pillager, game.state) == 3


def test_minecraft_wolf_pack_dynamic_attack_per_worker():
    game = Game(mode="minecraft")
    p1 = game.add_player("Pack")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    wolves = game.create_object(
        name=MINECRAFT_CARDS["Wolf Pack"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Wolf Pack"].characteristics,
        card_def=MINECRAFT_CARDS["Wolf Pack"],
    )
    wolves.controller = p1.id
    helper = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    helper.controller = p1.id

    # Wolf Pack 3 + 1 (per worker) = 4
    assert mc._mob_attack_power(wolves, game.state) == 4

    scout = game.create_object(
        name=MINECRAFT_CARDS["Alex's Scout"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Alex's Scout"].characteristics,
        card_def=MINECRAFT_CARDS["Alex's Scout"],
    )
    scout.controller = p1.id
    assert mc._mob_attack_power(wolves, game.state) == 5


def test_minecraft_creeper_deathrattle_deals_column_damage():
    game = Game(mode="minecraft")
    p1 = game.add_player("Boom")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.mc_materials.update({"wood": 5, "stone": 5})

    bed = _hand_card(game, p2.id, MINECRAFT_CARDS["Bed"])
    assert mc.play_card(game, p2.id, bed.id, cell={"x": 1, "y": 0})[0]

    creeper = game.create_object(
        name=MINECRAFT_CARDS["Creeper"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Creeper"].characteristics,
        card_def=MINECRAFT_CARDS["Creeper"],
    )
    creeper.controller = p1.id
    creeper.state.summoning_sickness = False
    blocker = game.create_object(
        name=MINECRAFT_CARDS["Snow Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Snow Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Snow Golem"],
    )
    blocker.controller = p2.id

    # Creeper (4/1) into Snow Golem (1/4): Creeper dies, blocker takes 4.
    ok, _msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": creeper.id, "target_column": 1}],
        auto_block=True,
    )
    assert ok
    # Creeper died, deathrattle hit frontmost in column 1 = Bed.
    assert creeper.zone == ZoneType.GRAVEYARD
    assert bed.state.damage == 3


def test_minecraft_wither_aoe_damages_opponent_grid():
    game = Game(mode="minecraft")
    p1 = game.add_player("Wither")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p2.mc_materials.update({"wood": 5, "stone": 5})

    bed = _hand_card(game, p2.id, MINECRAFT_CARDS["Bed"])
    wall = _hand_card(game, p2.id, MINECRAFT_CARDS["Cobblestone Wall"])
    assert mc.play_card(game, p2.id, bed.id, cell={"x": 1, "y": 0})[0]
    assert mc.play_card(game, p2.id, wall.id, cell={"x": 0, "y": 2})[0]

    # Spawn Wither directly to fire on_play (using create_object + emit play)
    p1.mc_materials.update({"redstone": 5, "diamond": 5})
    wither_card = _hand_card(game, p1.id, MINECRAFT_CARDS["Wither"])
    ok, _msg, _ = mc.play_card(game, p1.id, wither_card.id)
    assert ok
    assert bed.state.damage == 2
    assert wall.state.damage == 2


def test_minecraft_tnt_trap_deathrattle_blasts_avatar():
    game = Game(mode="minecraft")
    p1 = game.add_player("Trapper")
    p2 = game.add_player("Visitor")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"redstone": 2, "stone": 2})

    tnt = _hand_card(game, p1.id, MINECRAFT_CARDS["TNT Trap"])
    assert mc.play_card(game, p1.id, tnt.id, cell={"x": 0, "y": 2})[0]

    # Destroy the TNT directly via OBJECT_DESTROYED.
    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": tnt.id, "reason": "test"}))
    game.check_state_based_actions()
    assert p2.life == 16  # 20 - 4


def test_minecraft_aerial_attacker_cannot_be_blocked_by_ground():
    game = Game(mode="minecraft")
    p1 = game.add_player("Sky")
    p2 = game.add_player("Ground")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id

    ghast = game.create_object(
        name=MINECRAFT_CARDS["Ghast"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Ghast"].characteristics,
        card_def=MINECRAFT_CARDS["Ghast"],
    )
    ghast.controller = p1.id
    ghast.state.summoning_sickness = False
    grounded = game.create_object(
        name=MINECRAFT_CARDS["Wolf Pack"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Wolf Pack"].characteristics,
        card_def=MINECRAFT_CARDS["Wolf Pack"],
    )
    grounded.controller = p2.id

    # Manual block attempt: Wolf Pack tries to block Ghast — engine rejects.
    ok, _msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": ghast.id, "target_column": 0}],
        auto_block=False,
    )
    assert ok
    ok, _msg, _ = mc.declare_blockers(
        game, p2.id,
        [{"attacker_id": ghast.id, "blocker_id": grounded.id}],
    )
    assert ok
    # Block was discarded — Ghast went unblocked, Wolf Pack didn't engage.
    assert grounded.state.damage == 0
    assert ghast.state.damage == 0
    assert p2.life == 15  # 20 - 5 (Ghast)


def test_minecraft_reach_keyword_can_block_aerial():
    game = Game(mode="minecraft")
    p1 = game.add_player("Sky")
    p2 = game.add_player("Sniper")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id

    ghast = game.create_object(
        name=MINECRAFT_CARDS["Ghast"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Ghast"].characteristics,
        card_def=MINECRAFT_CARDS["Ghast"],
    )
    ghast.controller = p1.id
    ghast.state.summoning_sickness = False
    snow = game.create_object(
        name=MINECRAFT_CARDS["Snow Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Snow Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Snow Golem"],
    )
    snow.controller = p2.id

    ok, _msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": ghast.id, "target_column": 0}],
        auto_block=False,
    )
    assert ok
    ok, _msg, _ = mc.declare_blockers(
        game, p2.id,
        [{"attacker_id": ghast.id, "blocker_id": snow.id}],
    )
    assert ok
    # Snow Golem (HP 4) takes 4 (capped); overflow 1 → avatar.
    # Snow Golem chip on_block deals 1 to Ghast.
    assert snow.state.damage == 4
    assert ghast.state.damage == 2  # 1 chip + 1 combat
    assert p2.life == 19


def test_minecraft_overflow_damage_spills_to_column():
    game = Game(mode="minecraft")
    p1 = game.add_player("Big")
    p2 = game.add_player("Little")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.mc_materials.update({"wood": 5})

    bed = _hand_card(game, p2.id, MINECRAFT_CARDS["Bed"])
    assert mc.play_card(game, p2.id, bed.id, cell={"x": 0, "y": 0})[0]

    wither = game.create_object(
        name=MINECRAFT_CARDS["Wither"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Wither"].characteristics,
        card_def=MINECRAFT_CARDS["Wither"],
    )
    wither.controller = p1.id
    wither.state.summoning_sickness = False
    snow = game.create_object(
        name=MINECRAFT_CARDS["Snow Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Snow Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Snow Golem"],
    )
    snow.controller = p2.id

    # Wither attacks column 0 (where the Bed sits, no front-row defense yet).
    # Snow Golem blocks (it has reach).
    ok, _msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": wither.id, "target_column": 0}],
        auto_block=False,
    )
    assert ok
    # Wither AoE on play already hit the bed for 2; reset damage so we can verify overflow cleanly.
    bed.state.damage = 0
    ok, _msg, _ = mc.declare_blockers(
        game, p2.id,
        [{"attacker_id": wither.id, "blocker_id": snow.id}],
    )
    assert ok
    # Wither (8 ATK) capped at Snow Golem (HP 4) → 4 to Snow Golem; overflow 4 → Bed.
    assert snow.state.damage == 4
    assert bed.state.damage == 4


def test_minecraft_ai_skips_bad_block_when_attacker_hits_structure():
    """AI shouldn't chump-block a wall-targeting attacker if its blocker dies for nothing."""
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.mc_materials.update({"wood": 5, "stone": 5})
    # Defender has a dummy structure in column 0 so the attack is non-avatar.
    farm = _hand_card(game, p2.id, MINECRAFT_CARDS["Farm Plot"])
    assert mc.play_card(game, p2.id, farm.id, cell={"x": 0, "y": 1})[0]

    # Big attacker that would kill any cheap blocker.
    ravager = game.create_object(
        name=MINECRAFT_CARDS["Ravager"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Ravager"].characteristics,
        card_def=MINECRAFT_CARDS["Ravager"],
    )
    ravager.controller = p1.id
    ravager.state.summoning_sickness = False
    helper = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    helper.controller = p2.id

    # Attacker aims at column 0 (Farm Plot). With auto_block, AI defender should
    # decline to block — Steve's Helper would die for nothing.
    block_map = mc.auto_blockers(game.state, p2.id, [
        {"attacker_id": ravager.id, "target_column": 0}
    ])
    assert helper.id not in block_map.values()


def test_minecraft_ai_blocks_when_avatar_at_lethal():
    """If the avatar is about to die and there's no Bed, the AI should always block."""
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    p2.life = 6  # lethal range
    # No Bed for p2.

    ravager = game.create_object(
        name=MINECRAFT_CARDS["Ravager"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Ravager"].characteristics,
        card_def=MINECRAFT_CARDS["Ravager"],
    )
    ravager.controller = p1.id
    ravager.state.summoning_sickness = False
    helper = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    helper.controller = p2.id

    # Ravager (6 ATK) vs avatar at HP 6 = lethal. AI MUST block.
    block_map = mc.auto_blockers(game.state, p2.id, [
        {"attacker_id": ravager.id, "target_column": 0}
    ])
    assert block_map.get(ravager.id) == helper.id


def test_create_match_minecraft_sets_up_players_decks_and_state():
    async def _run():
        response = await create_match(
            request=CreateMatchRequest(
                mode="human_vs_bot",
                game_mode="minecraft",
                player_name="Tester",
                player_deck_id="builder",
                ai_deck_id="raider",
            ),
            background_tasks=BackgroundTasks(),
        )
        session = session_manager.get_session(response.match_id)
        assert session is not None
        assert session.game.state.game_mode == "minecraft"
        assert len(session.player_ids) == 2
        for pid in session.player_ids:
            player = session.game.state.players[pid]
            assert player.life == 20
            assert set(player.mc_materials) == set(mc.MATERIALS)
            assert len(session.game.state.minecraft_biomes[pid]) == 3
            assert len(session.game.state.minecraft_grid[pid]) == 3
            assert len(session.game.state.minecraft_grid[pid][0]) == 3
            assert len(session.game.state.zones[f"library_{pid}"].objects) == 50
        await session_manager.remove_session(response.match_id)

    asyncio.run(_run())
