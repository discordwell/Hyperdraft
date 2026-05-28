"""PKH NG+/depth-pass behavior tests."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cards.custom.pokemon_horizons import (
    POKEMON_HORIZONS_CARDS,
    PKH_WIRED_SPELL_AND_TOOL_CARDS,
)
from scripts.play.custom_set_depth_report import card_depth, summarize_set
from src.engine import (
    CardType,
    Characteristics,
    Color,
    Event,
    EventType,
    Game,
    ZoneType,
    get_power,
    get_toughness,
    has_ability,
)


DEPTH_UPGRADES = [
    "Sylveon, Intertwining Pokemon",
    "Lugia, Diving Pokemon",
    "Suicune, Aurora Pokemon",
    "Articuno, Freeze Pokemon",
    "Kyogre, Sea Basin Pokemon",
    "Gyarados",
    "Yveltal, Destruction Pokemon",
    "Absol, Disaster Pokemon",
    "Celebi, Time Travel Pokemon",
    "Nidoqueen",
]


PASS2_DEPTH_UPGRADES = [
    "Togetic",
    "Meowth",
    "Pidgey",
    "Rattata",
    "Raticate",
    "Wartortle",
    "Slowpoke",
    "Lapras",
    "Dewgong",
    "Staryu",
    "Walrein",
    "Haunter",
    "Grimer",
    "Weezing",
    "Koffing",
    "Misdreavus",
    "Mismagius",
    "Houndoom",
    "Houndour",
    "Zubat",
    "Charmeleon",
    "Flareon",
    "Jolteon",
    "Arcanine",
    "Growlithe",
    "Ninetales",
    "Vulpix",
    "Rapidash",
    "Ponyta",
    "Magmar",
    "Electabuzz",
    "Electivire",
    "Mankey",
    "Blaziken",
    "Infernape",
    "Ivysaur",
    "Victreebel",
    "Beedrill",
    "Scyther",
    "Nidoking",
]


def _put_on_battlefield(game: Game, player, card_name: str):
    card_def = POKEMON_HORIZONS_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone": f"hand_{player.id}",
            "from_zone_type": ZoneType.HAND,
            "to_zone": "battlefield",
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=obj.id,
        controller=player.id,
    ))
    return obj


def _put_in_hand(game: Game, player, name: str = "Filler"):
    return game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.CREATURE}),
    )


def _creature(game: Game, player, name: str, power: int, toughness: int, color=Color.GREEN):
    return game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Pokemon"},
            colors={color},
            power=power,
            toughness=toughness,
        ),
    )


def _land(game: Game, player, name: str):
    return game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.LAND}),
    )


def _depth_score(card_def) -> int:
    text = getattr(card_def, "text", "") or ""
    hooks = int(bool(getattr(card_def, "setup_interceptors", None)))
    hooks += int(bool(getattr(card_def, "resolve", None)))
    clauses = (
        text.count(".")
        + text.count("Whenever")
        + text.count("When ")
        + text.count("At the beginning")
        + text.count(":")
    )
    return hooks + clauses


def test_lugia_bounces_two_highest_impact_nonland_permanents():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    weak = _creature(game, p2, "Weak", 1, 1)
    mid = _creature(game, p2, "Mid", 3, 3)
    strong = _creature(game, p2, "Strong", 5, 5)
    land = _land(game, p2, "Opponent Island")

    _put_on_battlefield(game, p1, "Lugia, Diving Pokemon")

    assert strong.zone == ZoneType.HAND
    assert mid.zone == ZoneType.HAND
    assert weak.zone == ZoneType.BATTLEFIELD
    assert land.zone == ZoneType.BATTLEFIELD


def test_suicune_combat_damage_to_player_scries_then_draws():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    suicune = _put_on_battlefield(game, p1, "Suicune, Aurora Pokemon")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            "target": p2.id,
            "source": suicune.id,
            "amount": 3,
            "is_combat": True,
        },
        source=suicune.id,
        controller=p1.id,
    ))
    new_events = game.state.event_log[before:]

    assert any(e.type == EventType.SCRY and e.payload.get("count") == 2 for e in new_events)
    assert any(e.type == EventType.DRAW and e.payload.get("player") == p1.id for e in new_events)

    foe = _creature(game, p2, "Foe", 2, 2)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            "target": foe.id,
            "source": suicune.id,
            "amount": 3,
            "is_combat": True,
        },
        source=suicune.id,
        controller=p1.id,
    ))
    new_events = game.state.event_log[before:]
    assert not any(e.type in {EventType.SCRY, EventType.DRAW} for e in new_events)


def test_yveltal_destroys_the_largest_opposing_creature_on_etb():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    small = _creature(game, p2, "Small", 2, 2)
    large = _creature(game, p2, "Large", 6, 6)

    _put_on_battlefield(game, p1, "Yveltal, Destruction Pokemon")

    assert large.zone == ZoneType.GRAVEYARD
    assert small.zone == ZoneType.BATTLEFIELD


def test_absol_rewards_only_opponent_creature_deaths():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    _put_on_battlefield(game, p1, "Absol, Disaster Pokemon")
    enemy = _creature(game, p2, "Enemy", 2, 2)

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": enemy.id},
        source=enemy.id,
    ))
    new_events = game.state.event_log[before:]

    assert any(e.type == EventType.DRAW and e.payload.get("player") == p1.id for e in new_events)
    assert any(
        e.type == EventType.LIFE_CHANGE
        and e.payload.get("player") == p1.id
        and e.payload.get("amount") == -1
        for e in new_events
    )

    ally = _creature(game, p1, "Ally", 2, 2)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": ally.id},
        source=ally.id,
    ))
    new_events = game.state.event_log[before:]

    assert not any(e.type == EventType.DRAW and e.payload.get("player") == p1.id for e in new_events)
    assert not any(
        e.type == EventType.LIFE_CHANGE
        and e.payload.get("player") == p1.id
        and e.payload.get("amount") == -1
        for e in new_events
    )


def test_pass2_static_keyword_batch_is_query_backed():
    game = Game()
    p1 = game.add_player("P1")
    pidgey = _put_on_battlefield(game, p1, "Pidgey")
    blaziken = _put_on_battlefield(game, p1, "Blaziken")
    nidoking = _put_on_battlefield(game, p1, "Nidoking")

    assert has_ability(pidgey, "flying", game.state)
    assert has_ability(blaziken, "haste", game.state)
    assert has_ability(blaziken, "double strike", game.state)
    assert has_ability(nidoking, "trample", game.state)
    assert has_ability(nidoking, "deathtouch", game.state)


def test_pass2_evolve_updates_name_and_stats():
    game = Game()
    p1 = game.add_player("P1")
    vulpix = _put_on_battlefield(game, p1, "Vulpix")

    game.emit(Event(
        type=EventType.ACTIVATE,
        payload={"source": vulpix.id, "ability": "evolve"},
        source=vulpix.id,
        controller=p1.id,
    ))

    assert vulpix.name == "Ninetales"
    assert get_power(vulpix, game.state) == 3
    assert get_toughness(vulpix, game.state) == 3


def test_pass2_red_etb_damage_patterns_choose_deterministic_targets():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    ally = _creature(game, p1, "Ally", 3, 3)
    small = _creature(game, p2, "Small", 1, 1)
    large = _creature(game, p2, "Large", 5, 5)

    _put_on_battlefield(game, p1, "Magmar")

    assert large.state.damage == 2
    assert small.state.damage == 0
    assert ally.state.damage == 0

    _put_on_battlefield(game, p1, "Ninetales")

    assert large.state.damage == 4
    assert small.state.damage == 2
    assert ally.state.damage == 0


def test_pass2_blue_tap_and_black_discard_patterns():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    p3 = game.add_player("P3")
    weak = _creature(game, p2, "Weak", 1, 1)
    mid = _creature(game, p2, "Mid", 3, 3)
    strong = _creature(game, p3, "Strong", 5, 5)
    card_p2 = _put_in_hand(game, p2, "P2 card")
    card_p3 = _put_in_hand(game, p3, "P3 card")

    _put_on_battlefield(game, p1, "Walrein")

    assert strong.state.tapped
    assert mid.state.tapped
    assert not weak.state.tapped

    _put_on_battlefield(game, p1, "Mismagius")

    assert card_p2.zone == ZoneType.GRAVEYARD
    assert card_p3.zone == ZoneType.GRAVEYARD


def test_pass2_death_triggers_emit_engine_events():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    meowth = _put_on_battlefield(game, p1, "Meowth")
    koffing = _put_on_battlefield(game, p1, "Koffing")
    enemy = _creature(game, p2, "Enemy", 3, 3)

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": meowth.id},
        source=enemy.id,
    ))
    treasures = [
        obj for obj in game.state.objects.values()
        if obj.name == "Treasure" and obj.controller == p1.id and obj.zone == ZoneType.BATTLEFIELD
    ]
    assert len(treasures) == 1

    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": koffing.id},
        source=enemy.id,
    ))

    assert enemy.state.damage == 1


def test_pass3_potion_psychic_and_synthesis_resolve_to_engine_events():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.state.active_player = p1.id
    ally = _creature(game, p1, "Psychic ally", 2, 2, color=Color.BLUE)
    ally.characteristics.subtypes.add("Psychic")
    spell = game.create_object(
        name="Dummy spell",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(types={CardType.INSTANT}),
    )

    potion_events = POKEMON_HORIZONS_CARDS["Potion"].resolve([], game.state)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get("amount") == 3 for e in potion_events)
    assert any(e.type == EventType.SCRY and e.payload.get("count") == 1 for e in potion_events)
    assert any(e.type == EventType.DRAW and e.payload.get("player") == p1.id for e in potion_events)

    psychic_events = POKEMON_HORIZONS_CARDS["Psychic"].resolve([spell.id], game.state)
    assert any(e.type == EventType.COUNTER and e.payload.get("spell_id") == spell.id for e in psychic_events)
    assert any(e.type == EventType.SCRY for e in psychic_events)
    assert any(e.type == EventType.DRAW and e.payload.get("player") == p1.id for e in psychic_events)

    synthesis_events = POKEMON_HORIZONS_CARDS["Synthesis"].resolve([ally.id], game.state)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get("amount") == 5 for e in synthesis_events)
    assert any(
        e.type == EventType.COUNTER_ADDED
        and e.payload.get("object_id") == ally.id
        and e.payload.get("counter_type") == "+1/+1"
        for e in synthesis_events
    )


def test_pass3_tools_are_setup_and_equipment_query_backed():
    game = Game()
    p1 = game.add_player("P1")
    ally = _creature(game, p1, "Band carrier", 2, 2)
    band = _put_on_battlefield(game, p1, "Muscle Band")
    band.state.attached_to = ally.id

    assert get_power(ally, game.state) == 3
    assert get_toughness(ally, game.state) == 3
    assert has_ability(ally, "trample", game.state)
    assert has_ability(ally, "vigilance", game.state)

    _put_in_hand(game, p1, "Pokedex discard")
    pokedex = _put_on_battlefield(game, p1, "Pokedex")
    assert pokedex.state.activated_abilities
    events = pokedex.state.activated_abilities[0].effect_fn(pokedex, game.state, [])
    assert any(e.type == EventType.SCRY and e.payload.get("count") == 2 for e in events)
    assert any(e.type == EventType.DRAW and e.payload.get("player") == p1.id for e in events)
    assert any(e.type == EventType.DISCARD and e.payload.get("player") == p1.id for e in events)


def test_pass3_creature_triggers_cover_combat_and_damage_reflection():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    murkrow = _put_on_battlefield(game, p1, "Murkrow")
    card = _put_in_hand(game, p2, "Discard me")

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": p2.id, "source": murkrow.id, "amount": 2, "is_combat": True},
        source=murkrow.id,
        controller=p1.id,
    ))

    assert card.zone == ZoneType.GRAVEYARD

    wobbuffet = _put_on_battlefield(game, p1, "Wobbuffet")
    attacker = _creature(game, p2, "Attacker", 3, 3)

    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": wobbuffet.id, "source": attacker.id, "amount": 3},
        source=attacker.id,
        controller=p2.id,
    ))

    assert attacker.state.damage == 3


def test_pkh_does_not_use_setwide_research_boilerplate():
    cards = list(POKEMON_HORIZONS_CARDS.values())
    research_cards = [card for card in cards if "Research -" in (card.text or "")]

    assert research_cards == []


def test_pkh_wired_spell_and_tool_cards_have_resolve_or_setup():
    """Every card claimed to be wired by the PASS3 spell/tool pass has a resolve
    function or setup_interceptors. Replaces the legacy `PASS3_DEPTH_LIFTED`
    gate without enforcing the gamed depth_v2 metric."""
    for name in PKH_WIRED_SPELL_AND_TOOL_CARDS:
        cd = POKEMON_HORIZONS_CARDS.get(name)
        assert cd is not None, f"{name} not found in POKEMON_HORIZONS_CARDS"
        assert (
            getattr(cd, "setup_interceptors", None)
            or getattr(cd, "resolve", None)
        ), f"{name} wired by spell/tool pass but has neither setup_interceptors nor resolve"


def test_pkh_baseline_depth_remains_acceptable():
    """Soft baseline: most creatures have real interceptors. Replaces the
    previous PASS5_COMBO_WEB gate which inflated the wired count with
    pattern-based generic combo wrappers (the depth-rubber-stamp retrofit)."""
    cards = list(POKEMON_HORIZONS_CARDS.values())
    wired_cards = [
        cd for cd in cards
        if getattr(cd, "setup_interceptors", None) or getattr(cd, "resolve", None)
    ]
    assert all(getattr(POKEMON_HORIZONS_CARDS[name], "setup_interceptors", None) for name in DEPTH_UPGRADES)
    assert all(getattr(POKEMON_HORIZONS_CARDS[name], "setup_interceptors", None) for name in PASS2_DEPTH_UPGRADES)
    # The set has ~250 cards; a meaningful fraction (e.g. ~180+) must carry
    # a real implementation. Don't pin to a tight rubric-driven number.
    assert len(wired_cards) >= 180
