"""Beyond Ravnica Pokemon depth-pass behavior checks."""

from __future__ import annotations

import copy

from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
from src.cards.pokemon.beyond.ravnica.azorius import DOORKEEPER, TEFERI_HERO_OF_DOMINARIA
from src.cards.pokemon.beyond.ravnica.boros import GIDEON_BLACKBLADE
from src.cards.pokemon.beyond.ravnica.dimir import DUSKMANTLE_HOUSE_OF_SHADOW
from src.cards.pokemon.beyond.ravnica.golgari import VRASKA_GOLGARI_QUEEN
from src.cards.pokemon.beyond.ravnica.izzet import IZZET_SIGNET, NIVLET, NIV_MIZZETS_TOWER
from src.cards.pokemon.beyond.ravnica.orzhov import CARTEL_ARISTOCRAT, KAYA_GHOST_ASSASSIN, TITHE_DRINKER
from src.cards.pokemon.beyond.ravnica.rakdos import GORE_HOUSE_CHAINWALKER, TIBALT_RAKISH_INSTIGATOR
from src.cards.pokemon.beyond.ravnica.selesnya import SELESNYA_CLUESTONE, SAPROLING_SENTINEL
from src.cards.pokemon.beyond.ravnica.simic import (
    COILING_ORACLE,
    NOVIJEN_HEART_OF_PROGRESS,
    TRYGON_PREDATOR,
    VANNIFAR_EVOLVED_ENIGMA_EX,
    VANNIFUSE,
)
from src.cards.pokemon.sv_starter import FIRE_ENERGY, FIGHTING_ENERGY, GRASS_ENERGY
from src.engine.game import Game
from src.engine.types import Event, EventType, ZoneType


DEPTH_PASS_UPGRADES = {
    "Atarka Pup",
    "Aurelet",
    "Aurelin",
    "Bloodlet",
    "Cartel Aristocrat",
    "Drudge Beetle",
    "Doorkeeper",
    "Duskmantle, House of Shadow",
    "Etrata, the Silencer",
    "Gideon Blackblade",
    "Gore-House Chainwalker",
    "Jaradite",
    "Jarlet",
    "Kaya, Ghost Assassin",
    "Knight of Obligation",
    "Lazander",
    "Lazlet",
    "Mizzling",
    "Niv-Mizzet's Tower",
    "Nivlet",
    "Novijen, Heart of Progress",
    "Prime Speaker Zegana",
    "Rix Maadi, Dungeon Palace",
    "Selesnya Cluestone",
    "Skyknight Vanguard",
    "Soulsworn Spirit",
    "Sunhome, Fortress of the Legion",
    "Teferi, Hero of Dominaria",
    "Teyserin",
    "Teyslet",
    "Tibalt, Rakish Instigator",
    "Tomlet",
    "Trostavia",
    "Trostling",
    "Vannet",
    "Vannifuse",
    "Vitu-Ghazi, the City-Tree",
    "Vraska, Golgari Queen",
    "Watchwolf",
    "Wojek Halberdiers",
    "Trygon Predator",
}

DEPTH_TERMS = {
    "draw", "discard", "attach", "heal", "switch", "search", "shuffle",
    "place", "put", "mill", "damage counter", "benched", "active",
    "paralyzed", "asleep", "burned", "poisoned", "confused", "energy",
    "deck", "hand", "discard pile",
}


def make_game():
    game = Game(mode="pokemon")
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    return game, p1, p2


def place_card(game, player_id, card_def, zone_type):
    return game.create_object(
        card_def.name,
        player_id,
        zone_type,
        copy.deepcopy(card_def.characteristics),
        card_def,
    )


def stack_library(game, player_id, card_defs):
    zone = game.state.zones[f"library_{player_id}"]
    zone.objects.clear()
    for card_def in card_defs:
        place_card(game, player_id, card_def, ZoneType.LIBRARY)


def emit_draw_events(game, events):
    for event in events:
        if event.type == EventType.DRAW:
            game.pipeline.emit(event)


def attach_energy(game, pokemon, energy_def=FIRE_ENERGY):
    energy = place_card(game, pokemon.controller, energy_def, ZoneType.BATTLEFIELD)
    pokemon.state.attached_energy.append(energy.id)
    return energy


def test_teferi_bottoms_trainer_heals_then_draws_three():
    game, p1, _p2 = make_game()
    active = place_card(game, p1.id, NIVLET, ZoneType.ACTIVE_SPOT)
    active.state.damage_counters = 3
    payment = place_card(game, p1.id, IZZET_SIGNET, ZoneType.HAND)
    stack_library(game, p1.id, [FIRE_ENERGY, FIRE_ENERGY, FIRE_ENERGY])

    events = TEFERI_HERO_OF_DOMINARIA.resolve(
        Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id}, source="teferi"),
        game.state,
    )
    emit_draw_events(game, events)

    assert active.state.damage_counters == 1
    assert payment.id in game.state.zones[f"library_{p1.id}"].objects
    assert payment.zone == ZoneType.LIBRARY
    assert len(game.state.zones[f"hand_{p1.id}"].objects) == 3
    assert any(event.type == EventType.PKM_HEAL for event in events)


def test_gideon_marks_opponent_active_and_heals_yours():
    game, p1, p2 = make_game()
    own_active = place_card(game, p1.id, NIVLET, ZoneType.ACTIVE_SPOT)
    own_active.state.damage_counters = 3
    target = place_card(game, p2.id, SAPROLING_SENTINEL, ZoneType.ACTIVE_SPOT)

    events = GIDEON_BLACKBLADE.resolve(
        Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id}, source="gideon"),
        game.state,
    )

    assert target.state.damage_counters == 2
    assert own_active.state.damage_counters == 1
    assert any(event.type == EventType.PKM_PLACE_DAMAGE_COUNTERS for event in events)
    assert any(event.type == EventType.PKM_HEAL for event in events)


def test_kaya_shuffles_opponent_hand_and_marks_active():
    game, p1, p2 = make_game()
    target = place_card(game, p2.id, NIVLET, ZoneType.ACTIVE_SPOT)
    first = place_card(game, p2.id, FIRE_ENERGY, ZoneType.HAND)
    second = place_card(game, p2.id, IZZET_SIGNET, ZoneType.HAND)

    events = KAYA_GHOST_ASSASSIN.resolve(
        Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id}, source="kaya"),
        game.state,
    )

    assert game.state.zones[f"hand_{p2.id}"].objects == []
    assert {first.id, second.id} <= set(game.state.zones[f"library_{p2.id}"].objects)
    assert target.state.damage_counters == 1
    assert any(event.type == EventType.DRAW for event in events)


def test_vraska_recycles_discard_pokemon_and_trainer_payoffs():
    game, p1, p2 = make_game()
    active = place_card(game, p1.id, NIVLET, ZoneType.ACTIVE_SPOT)
    active.state.damage_counters = 3
    target = place_card(game, p2.id, SAPROLING_SENTINEL, ZoneType.ACTIVE_SPOT)
    trainer = place_card(game, p1.id, IZZET_SIGNET, ZoneType.GRAVEYARD)
    pokemon = place_card(game, p1.id, NIVLET, ZoneType.GRAVEYARD)
    energy = place_card(game, p1.id, FIRE_ENERGY, ZoneType.GRAVEYARD)

    events = VRASKA_GOLGARI_QUEEN.resolve(
        Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id}, source="vraska"),
        game.state,
    )

    assert game.state.zones[f"graveyard_{p1.id}"].objects == []
    assert {trainer.id, pokemon.id, energy.id} <= set(game.state.zones[f"library_{p1.id}"].objects)
    assert active.state.damage_counters == 1
    assert target.state.damage_counters == 1
    assert any(event.type == EventType.PKM_HEAL for event in events)


def test_duskmantle_confuses_player_who_mills_trainer():
    game, p1, p2 = make_game()
    p1_active = place_card(game, p1.id, NIVLET, ZoneType.ACTIVE_SPOT)
    p2_active = place_card(game, p2.id, SAPROLING_SENTINEL, ZoneType.ACTIVE_SPOT)
    stack_library(game, p1.id, [IZZET_SIGNET])
    stack_library(game, p2.id, [FIRE_ENERGY])

    events = DUSKMANTLE_HOUSE_OF_SHADOW.resolve(
        Event(type=EventType.PKM_PLAY_STADIUM, payload={"player": p1.id}, source="duskmantle"),
        game.state,
    )

    assert "confused" in p1_active.state.status_conditions
    assert "confused" not in p2_active.state.status_conditions
    assert len(game.state.zones[f"graveyard_{p1.id}"].objects) == 1
    assert len(game.state.zones[f"graveyard_{p2.id}"].objects) == 1
    assert any(event.type == EventType.PKM_APPLY_STATUS for event in events)


def test_novijen_attaches_energy_from_both_hands():
    game, p1, p2 = make_game()
    p1_active = place_card(game, p1.id, NIVLET, ZoneType.ACTIVE_SPOT)
    p2_active = place_card(game, p2.id, SAPROLING_SENTINEL, ZoneType.ACTIVE_SPOT)
    p1_energy = place_card(game, p1.id, FIRE_ENERGY, ZoneType.HAND)
    p2_energy = place_card(game, p2.id, GRASS_ENERGY, ZoneType.HAND)

    events = NOVIJEN_HEART_OF_PROGRESS.resolve(
        Event(type=EventType.PKM_PLAY_STADIUM, payload={"player": p1.id}, source="novijen"),
        game.state,
    )

    assert p1_active.state.attached_energy == [p1_energy.id]
    assert p2_active.state.attached_energy == [p2_energy.id]
    assert p1_energy.zone == ZoneType.BATTLEFIELD
    assert p2_energy.zone == ZoneType.BATTLEFIELD
    assert sum(1 for event in events if event.type == EventType.PKM_ATTACH_ENERGY) == 2


def test_gore_house_chainwalker_discards_for_bonus_damage():
    game, p1, p2 = make_game()
    attacker = place_card(game, p1.id, GORE_HOUSE_CHAINWALKER, ZoneType.ACTIVE_SPOT)
    target = place_card(game, p2.id, SAPROLING_SENTINEL, ZoneType.ACTIVE_SPOT)
    payment = place_card(game, p1.id, FIRE_ENERGY, ZoneType.HAND)

    events = GORE_HOUSE_CHAINWALKER.attacks[0]["effect_fn"](attacker, game.state)

    assert game.state.zones[f"hand_{p1.id}"].objects == []
    assert game.state.zones[f"graveyard_{p1.id}"].objects == [payment.id]
    assert target.state.damage_counters == 2
    assert any(event.type == EventType.PKM_DISCARD_ENERGY for event in events)


def test_vannifuse_stacks_next_evolution():
    game, p1, _p2 = make_game()
    attacker = place_card(game, p1.id, VANNIFUSE, ZoneType.ACTIVE_SPOT)
    stack_library(game, p1.id, [FIRE_ENERGY, VANNIFAR_EVOLVED_ENIGMA_EX])

    events = VANNIFUSE.attacks[0]["effect_fn"](attacker, game.state)

    top_id = game.state.zones[f"library_{p1.id}"].objects[0]
    assert game.state.objects[top_id].card_def is VANNIFAR_EVOLVED_ENIGMA_EX
    assert events == []


def test_doorkeeper_gate_tax_paralyzes_unenergized_active():
    game, p1, p2 = make_game()
    attacker = place_card(game, p1.id, DOORKEEPER, ZoneType.ACTIVE_SPOT)
    defender = place_card(game, p2.id, NIVLET, ZoneType.ACTIVE_SPOT)

    events = DOORKEEPER.attacks[0]["effect_fn"](attacker, game.state)

    assert defender.state.damage_counters == 1
    assert "paralyzed" in defender.state.status_conditions
    assert any(event.type == EventType.PKM_APPLY_STATUS for event in events)


def test_cartel_aristocrat_contract_bottoms_card_heals_and_drains():
    game, p1, p2 = make_game()
    aristocrat = place_card(game, p1.id, CARTEL_ARISTOCRAT, ZoneType.ACTIVE_SPOT)
    aristocrat.state.damage_counters = 3
    opponent = place_card(game, p2.id, TITHE_DRINKER, ZoneType.ACTIVE_SPOT)
    payment = place_card(game, p1.id, FIGHTING_ENERGY, ZoneType.HAND)

    events = CARTEL_ARISTOCRAT.ability["effect_fn"](aristocrat, game.state)

    assert payment.id not in game.state.zones[f"hand_{p1.id}"].objects
    assert game.state.zones[f"library_{p1.id}"].objects[-1] == payment.id
    assert payment.zone == ZoneType.LIBRARY
    assert aristocrat.state.damage_counters == 1
    assert opponent.state.damage_counters == 1
    assert aristocrat.state.ability_used_this_turn is True
    assert any(event.type == EventType.PKM_HEAL for event in events)

    assert CARTEL_ARISTOCRAT.ability["effect_fn"](aristocrat, game.state) == []


def test_selesnya_cluestone_attaches_when_board_is_wide():
    game, p1, _p2 = make_game()
    bench = [
        place_card(game, p1.id, SAPROLING_SENTINEL, ZoneType.BENCH)
        for _ in range(3)
    ]
    stack_library(game, p1.id, [GRASS_ENERGY, FIGHTING_ENERGY])

    events = SELESNYA_CLUESTONE.resolve(
        Event(type=EventType.PKM_PLAY_ITEM, payload={"player": p1.id}, source="cluestone"),
        game.state,
    )

    hand = game.state.zones[f"hand_{p1.id}"].objects
    assert len(hand) == 1
    assert len(bench[0].state.attached_energy) == 1
    assert len(game.state.zones[f"library_{p1.id}"].objects) == 0
    assert any(event.type == EventType.PKM_ATTACH_ENERGY for event in events)


def test_tibalt_mills_two_converts_trainers_to_damage_and_draws():
    game, p1, p2 = make_game()
    target = place_card(game, p2.id, NIVLET, ZoneType.ACTIVE_SPOT)
    place_card(game, p1.id, FIRE_ENERGY, ZoneType.HAND)
    stack_library(game, p1.id, [FIRE_ENERGY, FIRE_ENERGY])
    stack_library(game, p2.id, [IZZET_SIGNET, FIRE_ENERGY])

    events = TIBALT_RAKISH_INSTIGATOR.resolve(
        Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id}, source="tibalt"),
        game.state,
    )
    emit_draw_events(game, events)

    assert len(game.state.zones[f"graveyard_{p2.id}"].objects) == 2
    assert target.state.damage_counters == 1
    assert len(game.state.zones[f"graveyard_{p1.id}"].objects) == 1
    assert len(game.state.zones[f"hand_{p1.id}"].objects) == 2


def test_niv_mizzets_tower_draws_and_rewards_spent_trainers():
    game, p1, p2 = make_game()
    target = place_card(game, p2.id, NIVLET, ZoneType.ACTIVE_SPOT)
    place_card(game, p1.id, IZZET_SIGNET, ZoneType.GRAVEYARD)
    place_card(game, p1.id, SELESNYA_CLUESTONE, ZoneType.GRAVEYARD)
    stack_library(game, p1.id, [FIRE_ENERGY])
    stack_library(game, p2.id, [FIRE_ENERGY])

    events = NIV_MIZZETS_TOWER.resolve(
        Event(type=EventType.PKM_PLAY_STADIUM, payload={"player": p1.id}, source="tower"),
        game.state,
    )
    emit_draw_events(game, events)

    assert target.state.damage_counters == 2
    assert len(game.state.zones[f"hand_{p1.id}"].objects) == 1
    assert len(game.state.zones[f"hand_{p2.id}"].objects) == 1


def test_trygon_predator_moves_active_energy_to_opponent_bench():
    game, p1, p2 = make_game()
    attacker = place_card(game, p1.id, TRYGON_PREDATOR, ZoneType.ACTIVE_SPOT)
    opponent_active = place_card(game, p2.id, NIVLET, ZoneType.ACTIVE_SPOT)
    opponent_bench = place_card(game, p2.id, COILING_ORACLE, ZoneType.BENCH)
    energy = attach_energy(game, opponent_active, FIRE_ENERGY)

    events = TRYGON_PREDATOR.attacks[0]["effect_fn"](attacker, game.state)

    assert energy.id not in opponent_active.state.attached_energy
    assert opponent_bench.state.attached_energy == [energy.id]
    assert any(event.type == EventType.PKM_ATTACH_ENERGY for event in events)


def _depth_score(card) -> int:
    parts = [card.text or ""]
    if card.resolve:
        parts.append("resolve")
    if card.ability:
        parts.append(card.ability.get("text", ""))
        if card.ability.get("effect_fn"):
            parts.append("ability_effect")
    for attack in card.attacks:
        parts.append(attack.get("text", "") or "")
        if attack.get("effect_fn"):
            parts.append("attack_effect")

    blob = " ".join(parts).lower()
    term_hits = sum(1 for term in DEPTH_TERMS if term in blob)
    points = sum(1 for attack in card.attacks if attack.get("effect_fn"))
    points += 1 if card.resolve else 0
    points += 2 if card.ability and card.ability.get("effect_fn") else 0
    points += min(3, term_hits // 2)
    points += 1 if any(
        attack.get("text") and len(attack.get("text", "").split()) >= 10
        for attack in card.attacks
    ) else 0
    return points


def test_depth_pass_keeps_set_above_texture_gate():
    scores = {name: _depth_score(card) for name, card in BEYOND_RAVNICA_CARDS.items()}

    assert DEPTH_PASS_UPGRADES <= set(BEYOND_RAVNICA_CARDS)
    assert sum(scores.values()) >= 390
    assert sum(1 for score in scores.values() if score >= 4) >= 50
    assert sum(1 for score in scores.values() if score == 0) <= 12

    upgraded_without_rules = [
        name for name in DEPTH_PASS_UPGRADES
        if not (
            any(attack.get("effect_fn") for attack in BEYOND_RAVNICA_CARDS[name].attacks)
            or BEYOND_RAVNICA_CARDS[name].resolve
            or (
                BEYOND_RAVNICA_CARDS[name].ability
                and BEYOND_RAVNICA_CARDS[name].ability.get("effect_fn")
            )
        )
    ]
    assert upgraded_without_rules == []
