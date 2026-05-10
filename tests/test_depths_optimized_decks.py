from __future__ import annotations

from collections import Counter

from scripts.new_set._adapters.depths_tournament_adapter import (
    DEPTHS_STARTER_DECKS as TOURNAMENT_DEPTHS_DECKS,
    _aggregate,
    _card_ref,
    _collect_mechanic_triggers_from_log,
)
from src.cards.depths import ABYS_CARDS, DEPTHS_CARDS, SUBS_CARDS
from src.cards.depths.decks import (
    DEPTHS_OPTIMIZED_DECKS,
    DEPTHS_RESEARCH_MIDRANGE_SPEC,
    DEPTHS_STARTER_DECKS,
    format_depths_deck_labels,
    make_depths_research_midrange_deck,
    normalize_depths_deck_label,
)
from src.engine.game import Game
from src.engine.types import CardType, Event, EventType, ZoneType


def test_depths_research_midrange_is_registered_everywhere():
    assert "DEPTHS_research_midrange" in DEPTHS_OPTIMIZED_DECKS
    assert "DEPTHS_research_midrange" in DEPTHS_STARTER_DECKS
    assert "DEPTHS_research_midrange" in TOURNAMENT_DEPTHS_DECKS


def test_depths_deck_label_helpers_cover_expansion_and_optimized_decks():
    labels = format_depths_deck_labels()

    assert "ABYS_research" in labels
    assert "DEPTHS_research_midrange" in labels
    assert normalize_depths_deck_label("ABYS_research") == "ABYS_research"
    assert normalize_depths_deck_label("research") == "ABYS_research"
    assert (
        normalize_depths_deck_label("research_midrange")
        == "DEPTHS_research_midrange"
    )


def test_depths_research_midrange_is_legal_mixed_depths_deck():
    deck = make_depths_research_midrange_deck()

    assert len(deck) == 30
    assert sum(count for count, _name in DEPTHS_RESEARCH_MIDRANGE_SPEC) == 30
    assert all(card.name in DEPTHS_CARDS for card in deck)
    assert all(CardType.DEPTHS_VESSEL in card.characteristics.types for card in deck)

    names = Counter(card.name for card in deck)
    expected_names = Counter({
        name: count for count, name in DEPTHS_RESEARCH_MIDRANGE_SPEC
    })
    assert names == expected_names

    deck_names = set(names)
    assert deck_names & set(SUBS_CARDS)
    assert deck_names & set(ABYS_CARDS)
    assert {getattr(card, "domain", None) for card in deck} == {"SUBS", "ABYS"}


def _battlefield_object(game: Game, player_id: str, card):
    return game.create_object(
        name=card.name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card.characteristics,
        card_def=card,
    )


def test_depths_mechanic_triggers_do_not_count_abys_attacks_as_wolfpack():
    game = Game(mode="depths")
    player = game.add_player("Alice")
    attacker = _battlefield_object(game, player.id, ABYS_CARDS["Convoy Tender"])

    game.state.event_log.append(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": attacker.id},
        source=attacker.id,
        controller=player.id,
    ))

    triggers = _collect_mechanic_triggers_from_log(game.state)

    assert "WOLFPACK N (attack-trigger)" not in triggers


def test_depths_mechanic_triggers_count_wolfpack_attacks():
    game = Game(mode="depths")
    player = game.add_player("Alice")
    attacker = _battlefield_object(game, player.id, SUBS_CARDS["Pack Runner"])

    game.state.event_log.append(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": attacker.id},
        source=attacker.id,
        controller=player.id,
    ))

    triggers = _collect_mechanic_triggers_from_log(game.state)

    assert triggers["WOLFPACK N (attack-trigger)"] == 1


def test_depths_mechanic_triggers_count_abys_card_resupply_as_charge_swap():
    game = Game(mode="depths")
    player = game.add_player("Alice")
    source = _battlefield_object(game, player.id, ABYS_CARDS["Bathymetry Intern"])

    game.state.event_log.append(Event(
        type=EventType.DEPTHS_RESUPPLY,
        payload={
            "player": player.id,
            "sc_gained": 1,
            "reason": "abys_card_effect",
        },
        source=source.id,
        controller=player.id,
    ))

    triggers = _collect_mechanic_triggers_from_log(game.state)

    assert triggers["CHARGE-SWAP"] == 1


def test_depths_available_actions_omit_activate_without_capable_cards():
    result = _aggregate(
        ["ABYS_research"],
        raw_results=[],
        deck_specs={"ABYS_research": [ABYS_CARDS["Probe Scribe"]]},
    )

    assert "DEPTHS_ACTIVATE_ABILITY" not in result["available_actions"]


def test_depths_available_actions_include_activate_for_capable_cards():
    result = _aggregate(
        ["ABYS_salvage"],
        raw_results=[],
        deck_specs={"ABYS_salvage": [ABYS_CARDS["Winch Engine"]]},
    )

    assert "DEPTHS_ACTIVATE_ABILITY" in result["available_actions"]


def test_depths_mixed_deck_card_refs_use_source_set_for_coverage():
    abys_ref = _card_ref("DEPTHS_research_midrange", ABYS_CARDS["Sample Drone"])
    subs_ref = _card_ref("DEPTHS_research_midrange", SUBS_CARDS["U-Boat Wolf-cub"])

    assert abys_ref == "ABYS::Sample Drone"
    assert subs_ref == "SUBS::U-Boat Wolf-cub"
