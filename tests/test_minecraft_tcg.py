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


def test_minecraft_bed_persists_across_multiple_respawns():
    # Engine fact (iter-2 night_rush pilot finding): the Bed object is NOT
    # consumed by a respawn — only the avatar's gear is discarded. A single
    # Bed therefore protects the avatar across an unbounded number of deaths
    # until the Bed itself is destroyed. This test pins that behavior so a
    # future "consume Bed on respawn" change has to flag itself loudly.
    game = Game(mode="minecraft")
    p1 = game.add_player("Defender")
    p2 = game.add_player("Attacker")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"wood": 5})

    bed = _hand_card(game, p1.id, MINECRAFT_CARDS["Bed"])
    assert mc.play_card(game, p1.id, bed.id, cell={"x": 1, "y": 0})[0]
    assert mc.has_bed(game.state, p1.id)

    # Three sequential lethal hits — the Bed persists each time.
    for _ in range(3):
        game.emit(Event(type=EventType.DAMAGE, payload={"target": p1.id, "amount": 99}))
        game.check_state_based_actions()
        assert not p1.has_lost
        assert p1.life == 20
        assert mc.has_bed(game.state, p1.id)
        assert bed.zone == ZoneType.BATTLEFIELD

    # Once the Bed is destroyed, the next lethal hit kills.
    mc._move_object(game, bed, ZoneType.GRAVEYARD, source=bed.id)
    assert not mc.has_bed(game.state, p1.id)
    game.emit(Event(type=EventType.DAMAGE, payload={"target": p1.id, "amount": 99}))
    game.check_state_based_actions()
    assert p1.has_lost


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


def test_minecraft_declare_attackers_auto_block_consults_ai_handler():
    # Iter-2 night_rush pilot finding: when a human attacks via
    # `declare_attackers(auto_block=True)`, the engine used to call
    # `mc.auto_blockers` directly, bypassing the defending seat's bias preset
    # (e.g. block_mode="never" / "chump_anything"). The fix routes through
    # `game.turn_manager.minecraft_ai_handler.choose_blockers` first, mirroring
    # the explicit declare_blockers prompt path.
    game = Game(mode="minecraft")
    p1 = game.add_player("Attacker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id
    # Defender at lethal-risk HP with no Bed — `mc.auto_blockers` would chump
    # to save the avatar (avatar_lethal branch). A "never" handler must NOT.
    p2.life = 2

    attacker = game.create_object(
        name=MINECRAFT_CARDS["Zombie"].name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Zombie"].characteristics,
        card_def=MINECRAFT_CARDS["Zombie"],
    )
    attacker.controller = p1.id
    attacker.state.summoning_sickness = False

    blocker = game.create_object(
        name=MINECRAFT_CARDS["Skeleton Archer"].name,
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Skeleton Archer"].characteristics,
        card_def=MINECRAFT_CARDS["Skeleton Archer"],
    )
    blocker.controller = p2.id
    blocker.state.summoning_sickness = False

    # Attach a "never block" handler to the defending seat. Without the
    # routing fix, `auto_block=True` would still block the Zombie via
    # smart `auto_blockers` (avatar at lethal). With the fix, the
    # handler's choose_blockers governs and returns {}.
    handler = MinecraftAIAdapter(bias={"block_mode": "never"})
    game.turn_manager.set_ai_handler(handler)

    ok, _msg, _evs = mc.declare_attackers(
        game,
        p1.id,
        [{"attacker_id": attacker.id, "target_column": 1}],
        auto_block=True,
    )
    assert ok
    # Zombie 2 face damage lands unblocked: defender drops to 0, no Bed -> loses.
    assert p2.has_lost
    assert blocker.state.damage == 0  # blocker untouched (never engaged)


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


def test_minecraft_wither_etb_damages_opponent_avatar_per_hostile():
    """Wither's redesigned ETB: 2x hostile count to opponent's avatar."""
    game = Game(mode="minecraft")
    p1 = game.add_player("Wither")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    # Place 2 hostiles on p1's battlefield directly.
    z1 = game.create_object(
        name=MINECRAFT_CARDS["Zombie"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Zombie"].characteristics,
        card_def=MINECRAFT_CARDS["Zombie"],
    )
    z1.controller = p1.id
    s1 = game.create_object(
        name=MINECRAFT_CARDS["Spider"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Spider"].characteristics,
        card_def=MINECRAFT_CARDS["Spider"],
    )
    s1.controller = p1.id

    p1.mc_materials.update({"redstone": 5, "iron": 5})
    wither_card = _hand_card(game, p1.id, MINECRAFT_CARDS["Wither"])
    ok, _msg, _ = mc.play_card(game, p1.id, wither_card.id)
    assert ok
    # 2 hostiles * 2 = 4 damage to opponent's avatar (started at 20 -> 16).
    assert p2.life == 16


def test_minecraft_iron_golem_etb_damages_opponent_per_worker():
    game = Game(mode="minecraft")
    p1 = game.add_player("Worker")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    for name in ("Steve's Helper", "Alex's Scout", "Villager Mason"):
        w = game.create_object(
            name=MINECRAFT_CARDS[name].name,
            owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MINECRAFT_CARDS[name].characteristics,
            card_def=MINECRAFT_CARDS[name],
        )
        w.controller = p1.id

    p1.mc_materials.update({"iron": 3, "redstone": 3})
    ig = _hand_card(game, p1.id, MINECRAFT_CARDS["Iron Golem"])
    ok, _msg, _ = mc.play_card(game, p1.id, ig.id)
    assert ok
    # 3 workers * 2 = 6 damage to opponent's avatar.
    assert p2.life == 14


def test_minecraft_ender_dragon_etb_damages_per_diamond_permanent():
    game = Game(mode="minecraft")
    p1 = game.add_player("Diamond")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    # 2 diamond-cost permanents on p1's side: Diamond Pickaxe + Enchanting Table.
    for name in ("Diamond Pickaxe", "Enchanting Table"):
        cd = MINECRAFT_CARDS[name]
        obj = game.create_object(
            name=cd.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=cd.characteristics, card_def=cd,
        )
        obj.controller = p1.id

    p1.mc_materials.update({"iron": 5, "diamond": 5})
    ed = _hand_card(game, p1.id, MINECRAFT_CARDS["Ender Dragon"])
    ok, _msg, _ = mc.play_card(game, p1.id, ed.id)
    assert ok
    # 2 diamond-cost permanents * 2 damage = 4 to opponent.
    assert p2.life == 16


def test_minecraft_elder_guardian_pumps_workers_when_mining():
    from src.engine.queries import get_power
    game = Game(mode="minecraft")
    p1 = game.add_player("Workers")
    p2 = game.add_player("Idle")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    # Put Elder Guardian + a Worker on the field.
    eg = game.create_object(
        name=MINECRAFT_CARDS["Elder Guardian"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Elder Guardian"].characteristics,
        card_def=MINECRAFT_CARDS["Elder Guardian"],
    )
    eg.controller = p1.id
    worker = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    worker.controller = p1.id
    worker.state.summoning_sickness = False

    base_power = get_power(worker, game.state)
    # Mine via avatar (always allowed); the on_event hook fires for any
    # MC_MATERIAL_GAIN whose payload['player'] is the controller.
    ok, _msg, _evs = mc.mine_biome(game, p1.id, 0, avatar=True)
    assert ok
    pumped_power = get_power(worker, game.state)
    assert pumped_power == base_power + 1


def test_minecraft_ravager_gets_counter_when_block_destroyed():
    game = Game(mode="minecraft")
    p1 = game.add_player("Raider")
    p2 = game.add_player("Wall")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    rav = game.create_object(
        name=MINECRAFT_CARDS["Ravager"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Ravager"].characteristics,
        card_def=MINECRAFT_CARDS["Ravager"],
    )
    rav.controller = p1.id

    # Place a block on p2's grid, then destroy it.
    p2.mc_materials.update({"wood": 3})
    wall = _hand_card(game, p2.id, MINECRAFT_CARDS["Oak Planks"])
    assert mc.play_card(game, p2.id, wall.id, cell={"x": 0, "y": 2})[0]

    assert rav.state.counters.get("+1/+1", 0) == 0
    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={"object_id": wall.id, "reason": "test"}))
    assert rav.state.counters.get("+1/+1", 0) == 1


def test_minecraft_blaze_pumped_by_redstone_spend():
    from src.engine.queries import get_power
    game = Game(mode="minecraft")
    p1 = game.add_player("Pyro")
    p2 = game.add_player("Idle")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    blaze = game.create_object(
        name=MINECRAFT_CARDS["Blaze"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Blaze"].characteristics,
        card_def=MINECRAFT_CARDS["Blaze"],
    )
    blaze.controller = p1.id

    base_power = get_power(blaze, game.state)
    # Play any redstone-cost card to trigger the spend.
    p1.mc_materials.update({"stone": 5, "redstone": 5})
    lamp = _hand_card(game, p1.id, MINECRAFT_CARDS["Redstone Lamp"])
    assert mc.play_card(game, p1.id, lamp.id, cell={"x": 1, "y": 2})[0]
    pumped_power = get_power(blaze, game.state)
    assert pumped_power == base_power + 1


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

    # Use Warden (7 ATK) — high enough that overflow past Snow Golem (HP 4) reaches the Bed.
    warden = game.create_object(
        name=MINECRAFT_CARDS["Warden"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Warden"].characteristics,
        card_def=MINECRAFT_CARDS["Warden"],
    )
    warden.controller = p1.id
    warden.state.summoning_sickness = False
    snow = game.create_object(
        name=MINECRAFT_CARDS["Snow Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Snow Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Snow Golem"],
    )
    snow.controller = p2.id

    ok, _msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": warden.id, "target_column": 0}],
        auto_block=False,
    )
    assert ok
    ok, _msg, _ = mc.declare_blockers(
        game, p2.id,
        [{"attacker_id": warden.id, "blocker_id": snow.id}],
    )
    assert ok
    # Warden (7 ATK) capped at Snow Golem (HP 4) → 4 to Snow Golem; overflow 3 → Bed.
    assert snow.state.damage == 4
    assert bed.state.damage == 3


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


def test_phyrexian_compleated_upkeep_damages_controller():
    """Each Compleated mob you control deals 1 to your avatar at start of turn."""
    game = Game(mode="minecraft")
    p1 = game.add_player("Phyrexian")
    p2 = game.add_player("Bystander")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    negator = game.create_object(
        name=MINECRAFT_CARDS["Phyrexian Negator"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Phyrexian Negator"].characteristics,
        card_def=MINECRAFT_CARDS["Phyrexian Negator"],
    )
    negator.controller = p1.id
    walker = game.create_object(
        name=MINECRAFT_CARDS["Phyrexian Walker"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Phyrexian Walker"].characteristics,
        card_def=MINECRAFT_CARDS["Phyrexian Walker"],
    )
    walker.controller = p1.id

    initial_life = p1.life
    mc.apply_start_turn_bonuses(game, p1.id)
    # Two Compleated mobs → 2 damage to controller
    assert p1.life == initial_life - 2


def test_phyrexian_infect_keyword_adds_oil_counters():
    game = Game(mode="minecraft")
    p1 = game.add_player("Infector")
    p2 = game.add_player("Victim")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    game.state.active_player = p1.id

    mite = game.create_object(
        name=MINECRAFT_CARDS["Glistening Mite"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Glistening Mite"].characteristics,
        card_def=MINECRAFT_CARDS["Glistening Mite"],
    )
    mite.controller = p1.id
    mite.state.summoning_sickness = False

    ok, _msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": mite.id, "target_column": 0}],
        auto_block=True,
    )
    assert ok
    # Mite (2 ATK) hits avatar → 2 oil counters + 2 HP loss
    assert p2.mc_oil_counters == 2
    assert p2.life == 18


def test_phyrexian_five_oil_counters_loses_game():
    game = Game(mode="minecraft")
    p1 = game.add_player("Infector")
    p2 = game.add_player("Victim")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p2.mc_oil_counters = 5

    mc.handle_avatar_deaths(game)
    assert p2.has_lost


def test_phyrexian_glistening_oil_converts_low_hp_mob():
    game = Game(mode="minecraft")
    p1 = game.add_player("Caster")
    p2 = game.add_player("Owner")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"redstone": 5})

    # Steve's Helper has HP 2 — eligible for Glistening Oil.
    helper = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    helper.controller = p2.id

    oil = _hand_card(game, p1.id, MINECRAFT_CARDS["Glistening Oil"])
    ok, _msg, _ = mc.play_card(game, p1.id, oil.id, target_id=helper.id)
    assert ok
    assert helper.controller == p1.id
    assert "Compleated" in helper.characteristics.subtypes


def test_phyrexian_glistening_oil_rejects_high_hp_mob():
    game = Game(mode="minecraft")
    p1 = game.add_player("Caster")
    p2 = game.add_player("Owner")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"redstone": 5})

    iron = game.create_object(
        name=MINECRAFT_CARDS["Iron Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Iron Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Iron Golem"],
    )
    iron.controller = p2.id

    oil = _hand_card(game, p1.id, MINECRAFT_CARDS["Glistening Oil"])
    ok, _msg, _ = mc.play_card(game, p1.id, oil.id, target_id=iron.id)
    # Played but conversion failed; Iron Golem (HP 6) too tough.
    assert ok
    assert iron.controller == p2.id
    assert "Compleated" not in iron.characteristics.subtypes


def test_phyrexian_herobrine_destroys_target_mob():
    game = Game(mode="minecraft")
    p1 = game.add_player("Eye")
    p2 = game.add_player("Doomed")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"iron": 5, "redstone": 5, "diamond": 5})

    target = game.create_object(
        name=MINECRAFT_CARDS["Iron Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Iron Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Iron Golem"],
    )
    target.controller = p2.id

    herobrine = _hand_card(game, p1.id, MINECRAFT_CARDS["Herobrine, World's Eye"])
    ok, _msg, _ = mc.play_card(game, p1.id, herobrine.id, target_id=target.id)
    assert ok
    assert target.zone == ZoneType.GRAVEYARD
    assert "_my_" in MINECRAFT_CARDS["Herobrine, World's Eye"].text  # flavor preserved


def test_phyrexian_elesh_norn_lord_buffs_compleated():
    game = Game(mode="minecraft")
    p1 = game.add_player("Praetor")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    norn = game.create_object(
        name=MINECRAFT_CARDS["Elesh Norn, Grand Cenobite"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Elesh Norn, Grand Cenobite"].characteristics,
        card_def=MINECRAFT_CARDS["Elesh Norn, Grand Cenobite"],
    )
    norn.controller = p1.id
    walker = game.create_object(
        name=MINECRAFT_CARDS["Phyrexian Walker"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Phyrexian Walker"].characteristics,
        card_def=MINECRAFT_CARDS["Phyrexian Walker"],
    )
    walker.controller = p1.id

    # Walker base 1 ATK + Norn lord = 2 ATK
    assert mc._mob_attack_power(walker, game.state) == 2


def test_phyrexian_sheoldred_drains_on_play():
    game = Game(mode="minecraft")
    p1 = game.add_player("Whisperer")
    p2 = game.add_player("Victim")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"wood": 5, "iron": 5, "redstone": 5})
    p1.life = 12  # so we see heal effect

    sheo = _hand_card(game, p1.id, MINECRAFT_CARDS["Sheoldred, the Whispering One"])
    ok, _msg, _ = mc.play_card(game, p1.id, sheo.id)
    assert ok
    # Drain 5: opponent at 15, you back at 17
    assert p2.life == 15
    assert p1.life == 17


def test_phyrexian_compleated_dominion_deck_loads():
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS, MINECRAFT_CARDS
    deck = MINECRAFT_STARTER_DECKS["compleated_dominion"]()
    assert len(deck) == 50
    names = {card.name for card in deck}
    # Showcases Phyrexia: at least 2 praetors and Herobrine
    praetors = {n for n in names if "Praetor" in MINECRAFT_CARDS[n].characteristics.subtypes}
    assert len(praetors) >= 2
    assert "Herobrine, World's Eye" in names


def test_phyrexian_negator_sacrifices_when_damaged():
    """Negator (5/5 for 2 wood) must sacrifice another mob when dealt damage."""
    game = Game(mode="minecraft")
    p1 = game.add_player("Phyrexian")
    p2 = game.add_player("Attacker")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    negator = game.create_object(
        name=MINECRAFT_CARDS["Phyrexian Negator"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Phyrexian Negator"].characteristics,
        card_def=MINECRAFT_CARDS["Phyrexian Negator"],
    )
    negator.controller = p1.id
    fodder = game.create_object(
        name=MINECRAFT_CARDS["Phyrexian Walker"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Phyrexian Walker"].characteristics,
        card_def=MINECRAFT_CARDS["Phyrexian Walker"],
    )
    fodder.controller = p1.id

    # Deal 1 damage — fodder should be sacrificed; Negator survives.
    game.emit(Event(type=EventType.DAMAGE, payload={"target": negator.id, "amount": 1, "source": p2.id}))
    game.check_state_based_actions()
    assert fodder.zone == ZoneType.GRAVEYARD
    assert negator.zone == ZoneType.BATTLEFIELD


def test_phyrexian_negator_destroys_self_with_no_fodder():
    """If no other mobs to sac, Negator destroys itself."""
    game = Game(mode="minecraft")
    p1 = game.add_player("Phyrexian")
    p2 = game.add_player("Attacker")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    negator = game.create_object(
        name=MINECRAFT_CARDS["Phyrexian Negator"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Phyrexian Negator"].characteristics,
        card_def=MINECRAFT_CARDS["Phyrexian Negator"],
    )
    negator.controller = p1.id

    game.emit(Event(type=EventType.DAMAGE, payload={"target": negator.id, "amount": 1, "source": p2.id}))
    game.check_state_based_actions()
    assert negator.zone == ZoneType.GRAVEYARD


def test_phyrexian_compleated_creeper_deathrattle_restored():
    """Compleated Creeper's deathrattle deals 4 to its column on death."""
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
        name=MINECRAFT_CARDS["Compleated Creeper"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Compleated Creeper"].characteristics,
        card_def=MINECRAFT_CARDS["Compleated Creeper"],
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

    ok, _msg, _ = mc.declare_attackers(
        game, p1.id,
        [{"attacker_id": creeper.id, "target_column": 1}],
        auto_block=True,
    )
    assert ok
    # Creeper dies (1 chip + 1 combat = 2 dmg). Bed eats overflow 1 (Creeper 5
    # ATK vs Snow Golem 4 HP) plus 4 from the deathrattle = 5 total.
    assert creeper.zone == ZoneType.GRAVEYARD
    assert bed.state.damage == 5


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


# ===========================================================================
# Box of Horrors set
# ===========================================================================

def _put_in_hand(game, player_id, card_def):
    """Like _hand_card, but also registers the object in the hand zone (since
    create_object only sets obj.zone, the zone listing is updated by the
    pipeline on real plays). For Horror discard tests we need a populated
    hand_{player} zone so _opp_discard can target newest-first.
    """
    obj = game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    hand = game.state.zones.get(f"hand_{player_id}")
    if hand and obj.id not in hand.objects:
        hand.objects.append(obj.id)
    return obj


def test_horror_whispering_curse_discards_newest_card():
    game = Game(mode="minecraft")
    p1 = game.add_player("Caster")
    p2 = game.add_player("Victim")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"redstone": 3})

    # Stack p2's hand: oldest -> newest. Curse should hit the rightmost (newest).
    older = _put_in_hand(game, p2.id, MINECRAFT_CARDS["Bed"])
    newer = _put_in_hand(game, p2.id, MINECRAFT_CARDS["Iron Sword"])

    curse = _hand_card(game, p1.id, MINECRAFT_CARDS["Whispering Curse"])
    p1_hand = game.state.zones.get(f"hand_{p1.id}")
    if curse.id not in p1_hand.objects:
        p1_hand.objects.append(curse.id)
    ok, _msg, _ = mc.play_card(game, p1.id, curse.id)
    assert ok
    assert newer.zone == ZoneType.GRAVEYARD
    assert older.zone == ZoneType.HAND


def test_horror_wither_skeleton_attack_drops_target_toughness_permanently():
    game = Game(mode="minecraft")
    p1 = game.add_player("Wither")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    skeleton = game.create_object(
        name=MINECRAFT_CARDS["Wither Skeleton"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Wither Skeleton"].characteristics,
        card_def=MINECRAFT_CARDS["Wither Skeleton"],
    )
    skeleton.controller = p1.id

    target = game.create_object(
        name=MINECRAFT_CARDS["Iron Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Iron Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Iron Golem"],
    )
    target.controller = p2.id
    base_tough = target.characteristics.toughness
    # Trigger the on_attack hook directly with a target-mob payload.
    hook = MINECRAFT_CARDS["Wither Skeleton"].mc_on_attack
    events = hook(skeleton, game.state, target.id) or []
    # Effect mutates state synchronously; events list may be empty.
    assert target.characteristics.toughness == base_tough - 1
    # Avatar payloads are ignored.
    hook(skeleton, game.state, p2.id)
    assert target.characteristics.toughness == base_tough - 1


def test_horror_endermite_cluster_deathrattle_summons_token():
    game = Game(mode="minecraft")
    p1 = game.add_player("Cluster")
    p2 = game.add_player("Other")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    cluster = game.create_object(
        name=MINECRAFT_CARDS["Endermite Cluster"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Endermite Cluster"].characteristics,
        card_def=MINECRAFT_CARDS["Endermite Cluster"],
    )
    cluster.controller = p1.id
    battlefield_before = set(game.state.zones["battlefield"].objects)

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": cluster.id, "reason": "test"}))
    game.check_state_based_actions()

    new_objs = set(game.state.zones["battlefield"].objects) - battlefield_before
    spawned = [game.state.objects[oid] for oid in new_objs]
    assert any(o.characteristics.power == 1 and "Horror" in o.characteristics.subtypes
               for o in spawned)


def test_horror_lost_soul_deathrattle_draws():
    game = Game(mode="minecraft")
    p1 = game.add_player("Bereaved")
    p2 = game.add_player("Other")
    # Stack a deck so DRAW finds a card.
    deck = [MINECRAFT_CARDS["Bed"]]
    game.setup_minecraft_player(p1, deck)
    game.setup_minecraft_player(p2, [])
    hand_before = len(game.state.zones[f"hand_{p1.id}"].objects)

    soul = game.create_object(
        name=MINECRAFT_CARDS["Lost Soul"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Lost Soul"].characteristics,
        card_def=MINECRAFT_CARDS["Lost Soul"],
    )
    soul.controller = p1.id

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                    payload={"object_id": soul.id, "reason": "test"}))
    game.check_state_based_actions()
    assert len(game.state.zones[f"hand_{p1.id}"].objects) == hand_before + 1


def test_horror_old_watcher_lord_buffs_other_horrors():
    game = Game(mode="minecraft")
    p1 = game.add_player("Watcher")
    p2 = game.add_player("Other")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])

    watcher = game.create_object(
        name=MINECRAFT_CARDS["The Old Watcher"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["The Old Watcher"].characteristics,
        card_def=MINECRAFT_CARDS["The Old Watcher"],
    )
    watcher.controller = p1.id

    crawler = game.create_object(
        name=MINECRAFT_CARDS["Cave Crawler"].name,
        owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Cave Crawler"].characteristics,
        card_def=MINECRAFT_CARDS["Cave Crawler"],
    )
    crawler.controller = p1.id

    # Cave Crawler base 4 ATK + Watcher's +1 lord = 5
    assert mc._mob_attack_power(crawler, game.state) == 5


def test_horror_drag_to_the_dark_only_kills_low_hp():
    game = Game(mode="minecraft")
    p1 = game.add_player("Caster")
    p2 = game.add_player("Owner")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"wood": 5, "redstone": 5})

    # Helper has HP 2 — eligible for Drag to the Dark (threshold 3).
    helper = game.create_object(
        name=MINECRAFT_CARDS["Steve's Helper"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
        card_def=MINECRAFT_CARDS["Steve's Helper"],
    )
    helper.controller = p2.id

    drag = _hand_card(game, p1.id, MINECRAFT_CARDS["Drag to the Dark"])
    ok, _msg, _ = mc.play_card(game, p1.id, drag.id, target_id=helper.id)
    assert ok
    assert helper.zone == ZoneType.GRAVEYARD

    # Iron Golem (HP 6) ignores it.
    p1.mc_materials.update({"wood": 5, "redstone": 5})
    iron = game.create_object(
        name=MINECRAFT_CARDS["Iron Golem"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Iron Golem"].characteristics,
        card_def=MINECRAFT_CARDS["Iron Golem"],
    )
    iron.controller = p2.id
    drag2 = _hand_card(game, p1.id, MINECRAFT_CARDS["Drag to the Dark"])
    ok, _msg, _ = mc.play_card(game, p1.id, drag2.id, target_id=iron.id)
    assert ok
    assert iron.zone == ZoneType.BATTLEFIELD


def test_horror_possession_steals_low_hp_mob():
    game = Game(mode="minecraft")
    p1 = game.add_player("Caster")
    p2 = game.add_player("Owner")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"iron": 5, "redstone": 5})

    # Allay Courier has HP 2 — eligible.
    allay = game.create_object(
        name=MINECRAFT_CARDS["Allay Courier"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Allay Courier"].characteristics,
        card_def=MINECRAFT_CARDS["Allay Courier"],
    )
    allay.controller = p2.id

    poss = _hand_card(game, p1.id, MINECRAFT_CARDS["Possession"])
    ok, _msg, _ = mc.play_card(game, p1.id, poss.id, target_id=allay.id)
    assert ok
    assert allay.controller == p1.id
    assert "Horror" in allay.characteristics.subtypes


def test_horror_mimicer_gains_power_from_target():
    game = Game(mode="minecraft")
    p1 = game.add_player("Mimic")
    p2 = game.add_player("Subject")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"wood": 5, "redstone": 5})

    # Wolf Pack base 3 ATK; Mimicer should grow by +3/+3.
    wolf = game.create_object(
        name=MINECRAFT_CARDS["Wolf Pack"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Wolf Pack"].characteristics,
        card_def=MINECRAFT_CARDS["Wolf Pack"],
    )
    wolf.controller = p2.id

    p1.mc_materials.update({"iron": 5, "diamond": 5})
    mimic = _hand_card(game, p1.id, MINECRAFT_CARDS["The Mimicer"])
    base_p = mimic.characteristics.power
    base_t = mimic.characteristics.toughness
    ok, _msg, _ = mc.play_card(game, p1.id, mimic.id, target_id=wolf.id)
    assert ok
    assert mimic.characteristics.power == base_p + 3
    assert mimic.characteristics.toughness == base_t + 3


def test_horror_wither_storm_aoe_hits_grid_and_mobs():
    game = Game(mode="minecraft")
    p1 = game.add_player("Storm")
    p2 = game.add_player("Defender")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"stone": 5, "iron": 5, "redstone": 5, "diamond": 5})
    p2.mc_materials.update({"wood": 5, "stone": 5})

    bed = _hand_card(game, p2.id, MINECRAFT_CARDS["Bed"])
    assert mc.play_card(game, p2.id, bed.id, cell={"x": 1, "y": 0})[0]

    zombie = game.create_object(
        name=MINECRAFT_CARDS["Zombie"].name,
        owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=MINECRAFT_CARDS["Zombie"].characteristics,
        card_def=MINECRAFT_CARDS["Zombie"],
    )
    zombie.controller = p2.id

    storm = _hand_card(game, p1.id, MINECRAFT_CARDS["Wither Storm"])
    ok, _msg, _ = mc.play_card(game, p1.id, storm.id)
    assert ok
    assert bed.state.damage == 1
    assert zombie.state.damage == 1


def test_horror_box_of_horrors_deck_loads():
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS, MINECRAFT_CARDS
    deck = MINECRAFT_STARTER_DECKS["box_of_horrors"]()
    assert len(deck) == 60  # 30 names × 2 copies each
    names = {card.name for card in deck}
    horror_mobs = {n for n in names
                   if "Horror" in MINECRAFT_CARDS[n].characteristics.subtypes
                   and CardType.MC_MOB in MINECRAFT_CARDS[n].characteristics.types}
    assert len(horror_mobs) >= 8  # plenty of horror tribal anchors
    assert "Cave Dweller" in names
    assert "The Man From The Fog" in names


def test_passive_econ_worker_bonus_cap_pivots_off_workers():
    """
    With worker_bonus_cap=2 and 2 Workers already on the field, the
    +80 worker_bonus_under_3 must NOT fire — so a Zombie (cheap mob)
    out-scores a third Steve's Helper. Regression test for iter-3
    night_rush game where the AI played a 2nd Steve at 6 HP under
    pressure instead of pivoting to a defensive mob.
    """
    from src.ai.minecraft_adapter import MinecraftAIAdapter, MC_BIAS_PRESETS

    game = Game(mode="minecraft")
    p1 = game.add_player("AI")
    p2 = game.add_player("Opp")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    p1.mc_materials.update({"wood": 5, "stone": 5})

    # Two Workers already on battlefield → the cap should clamp to off.
    for _ in range(2):
        w = game.create_object(
            name=MINECRAFT_CARDS["Steve's Helper"].name,
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=MINECRAFT_CARDS["Steve's Helper"].characteristics,
            card_def=MINECRAFT_CARDS["Steve's Helper"],
        )
        w.controller = p1.id

    # Hand: 3rd Worker (Steve) competing with a Zombie (1W cheap mob).
    _hand_card(game, p1.id, MINECRAFT_CARDS["Steve's Helper"])
    zombie_in_hand = _hand_card(game, p1.id, MINECRAFT_CARDS["Zombie"])

    # passive_econ has worker_bonus_cap=2 — third Worker bonus must not fire.
    adapter = MinecraftAIAdapter(bias="passive_econ")
    chosen = adapter._choose_card_to_play(game.state, p1.id)
    assert chosen == zombie_in_hand.id, (
        "passive_econ should pivot to Zombie once worker_bonus_cap is hit"
    )

    # Sanity: balanced (no cap) keeps preferring Workers under 3.
    balanced = MinecraftAIAdapter(bias="balanced")
    chosen_bal = balanced._choose_card_to_play(game.state, p1.id)
    chosen_obj = game.state.objects.get(chosen_bal)
    assert chosen_obj is not None
    assert "Worker" in chosen_obj.characteristics.subtypes, (
        "balanced (worker_bonus_cap=0) should still pick the third Worker"
    )

    # Verify the preset itself documents the new knob.
    assert MC_BIAS_PRESETS["passive_econ"]["worker_bonus_cap"] == 2
    assert MC_BIAS_PRESETS["balanced"]["worker_bonus_cap"] == 0
