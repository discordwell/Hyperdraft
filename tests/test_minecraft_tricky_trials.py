from src.engine.game import Game
from src.engine.types import CardType, Event, EventType, ZoneType
from src.engine import minecraft as mc
from src.cards.minecraft import (
    ALPHA_CARDS,
    HORROR_CARDS,
    MINECRAFT_CARDS,
    MINECRAFT_STARTER_DECKS,
    MCT_CARDS,
    PHYREXIA_CARDS,
)


def _build_game():
    game = Game(mode="minecraft")
    p1 = game.add_player("MCT Pilot")
    p2 = game.add_player("Baseline")
    game.setup_minecraft_player(p1, [])
    game.setup_minecraft_player(p2, [])
    return game, p1, p2


def _hand_card(game, player_id, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.controller = player_id
    return obj


def _battlefield_card(game, player_id, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.controller = player_id
    return obj


def test_mct_set_size_and_starter_decks_are_registered():
    assert len(MCT_CARDS) == 200
    assert all(getattr(card, "mc_set_code", None) == "MCT" for card in MCT_CARDS.values())

    for name in [
        "trial_chambers",
        "tamed_trails",
        "copper_pulse",
        "deep_dark_echo",
        "bastion_raid",
        "end_voyage",
    ]:
        deck = MINECRAFT_STARTER_DECKS[name]()
        assert len(deck) == 50
        assert len({card.name for card in deck}) == 25


def test_ender_warboss_midrange_is_registered_legal_and_cross_set():
    deck = MINECRAFT_STARTER_DECKS["ender_warboss_midrange"]()
    names = [card.name for card in deck]
    unique_names = set(names)
    old_names = set(ALPHA_CARDS) | set(PHYREXIA_CARDS) | set(HORROR_CARDS)

    assert len(deck) == 50
    assert len(unique_names) == 25
    assert all(names.count(name) == 2 for name in unique_names)
    assert unique_names & old_names
    assert unique_names & set(MCT_CARDS)


def test_trial_reward_turns_on_with_trial_permanent():
    game, p1, _p2 = _build_game()
    _battlefield_card(game, p1.id, MINECRAFT_CARDS["Trial Spawner"])
    p1.mc_materials.update({"iron": 1})

    card = _hand_card(game, p1.id, MINECRAFT_CARDS["Chamber Rewards"])
    ok, message, events = mc.play_card(game, p1.id, card.id)

    assert ok, message
    assert p1.mc_materials["wood"] == 1
    assert p1.mc_materials["stone"] == 1
    assert any(event.type == EventType.DRAW for event in events)


def test_pulse_reacts_to_redstone_spend():
    game, p1, _p2 = _build_game()
    _battlefield_card(game, p1.id, MINECRAFT_CARDS["Copper Bulb"])

    game.emit(Event(
        type=EventType.MC_MATERIAL_SPEND,
        payload={"player": p1.id, "materials": {"redstone": 1}},
        source="test",
    ))

    assert any(event.type == EventType.DRAW for event in game.state.event_log)


def test_echo_reacts_to_mob_death_with_token():
    game, p1, p2 = _build_game()
    _battlefield_card(game, p1.id, MINECRAFT_CARDS["Echo Shrieker"])
    victim = _battlefield_card(game, p2.id, MINECRAFT_CARDS["Zombie"])

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": victim.id, "reason": "test"},
        source="test",
    ))

    assert any(event.type == EventType.CREATE_TOKEN for event in game.state.event_log)


def test_tame_pack_bonus_counts_unique_friends_once():
    game, p1, _p2 = _build_game()
    leader = _battlefield_card(game, p1.id, MINECRAFT_CARDS["Pack Leader"])
    _battlefield_card(game, p1.id, MINECRAFT_CARDS["Wolf Companion"])
    _battlefield_card(game, p1.id, MINECRAFT_CARDS["Cat Familiar"])

    assert mc._mob_attack_power(leader, game.state) == 4


def test_end_voyage_dynamic_bonus_scales_with_end_board_and_diamonds():
    game, p1, _p2 = _build_game()
    p1.mc_materials["diamond"] = 2
    sovereign = _battlefield_card(game, p1.id, MINECRAFT_CARDS["Ender Sovereign"])
    _battlefield_card(game, p1.id, MINECRAFT_CARDS["Enderling"])
    _battlefield_card(game, p1.id, MINECRAFT_CARDS["End Scout"])

    assert CardType.MC_MOB in sovereign.characteristics.types
    assert mc._mob_attack_power(sovereign, game.state) == 11


# ─── Phase 4 demo: _damage_target emits PendingChoice ─────────────────────


def test_mct_damage_target_emits_pending_choice_when_target_id_omitted():
    """Phase 4 demo: MCT ``_damage_target`` (used by Breeze Charge, Wind Burst,
    Trial Cleave, Sonic Boom, etc.) now emits a ``PendingChoice`` over the
    opponent's frontmost-per-column mobs plus the avatar fallback when the
    caller does not pre-resolve a target. Locks in:
    (1) Choice options cover every frontmost mob (one per column) plus avatar.
    (2) For human controllers, the choice stays pending (returns []).
    (3) The ``heuristic_pick`` preserves the old AI behavior (first-found
        frontmost mob across columns).
    """
    from src.cards.minecraft.tricky_trials import _damage_target

    game, p1, p2 = _build_game()
    # Place two frontline mobs on p2's grid in different columns. The
    # column iteration walks columns 0..2 left-to-right, and within each
    # column the "front" is the highest y. We place at (x=0, y=2) and
    # (x=2, y=2) so both are frontmost in their column.
    mob_a = _battlefield_card(game, p2.id, MINECRAFT_CARDS["Zombie"])
    mob_a.state.mc_grid_x = 0
    mob_a.state.mc_grid_y = 2
    game.state.minecraft_grid[p2.id][2][0] = mob_a.id

    mob_b = _battlefield_card(game, p2.id, MINECRAFT_CARDS["Zombie"])
    mob_b.state.mc_grid_x = 2
    mob_b.state.mc_grid_y = 2
    game.state.minecraft_grid[p2.id][2][2] = mob_b.id

    # An attacking action played by p1 with no pre-resolved target.
    source = _battlefield_card(game, p1.id, MINECRAFT_CARDS["Trial Spawner"])
    effect = _damage_target(3)
    events = effect(source, game.state, target_id=None)

    # Human path: choice stays pending, no events yet.
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    assert pc.player == p1.id
    assert pc.source_id == source.id
    option_ids = {opt["id"] for opt in pc.options}
    # Both frontline mobs + the avatar are choosable.
    assert mob_a.id in option_ids
    assert mob_b.id in option_ids
    assert p2.id in option_ids
    # heuristic_pick == first-found frontmost mob (column 0 wins).
    hp = pc.callback_data.get("heuristic_pick")
    assert hp == [mob_a.id]


def test_mct_damage_target_short_circuits_when_no_opponent():
    """No live opponent → no-op (empty events, no pending choice)."""
    from src.cards.minecraft.tricky_trials import _damage_target

    game, p1, p2 = _build_game()
    p2.has_lost = True  # opponent eliminated
    game.state.pending_choice = None

    source = _battlefield_card(game, p1.id, MINECRAFT_CARDS["Trial Spawner"])
    events = _damage_target(2)(source, game.state, target_id=None)
    assert events == []
    assert game.state.pending_choice is None


def test_mct_damage_target_uses_preresolved_target_id_without_choice():
    """When ``play_card`` already resolved ``target_id`` from ``target_column``
    on the frontend, the effect bypasses the PendingChoice path and emits
    DAMAGE directly. Preserves the existing column-target flow."""
    from src.cards.minecraft.tricky_trials import _damage_target

    game, p1, p2 = _build_game()
    target_mob = _battlefield_card(game, p2.id, MINECRAFT_CARDS["Zombie"])
    target_mob.state.mc_grid_x = 1
    target_mob.state.mc_grid_y = 2
    game.state.minecraft_grid[p2.id][2][1] = target_mob.id
    game.state.pending_choice = None

    source = _battlefield_card(game, p1.id, MINECRAFT_CARDS["Trial Spawner"])
    events = _damage_target(4)(source, game.state, target_id=target_mob.id)

    assert game.state.pending_choice is None
    assert len(events) == 1
    assert events[0].type == EventType.DAMAGE
    assert events[0].payload["target"] == target_mob.id
    assert events[0].payload["amount"] == 4
