"""Auto-generated interceptor verification for Lost Caverns of Ixalan (LCI).

Per /test-interceptors skill — fires each card's expected trigger event in
isolation and asserts that the card's effect_fn either:
  (a) emits at least one Event (effect actually fires), OR
  (b) opens a PendingChoice (target-choice cards open a UI prompt), OR
  (c) mutates the game state in an observable way.

Cards that fire a trigger but emit no events and open no choice and mutate
no state are flagged — these are the "depths trap" interceptors per
CLAUDE.md (interceptor wired, engine doesn't support effect, effect_fn
returns []).

Style scaffolding:
  ETB         -> ZONE_CHANGE(to_zone_type=BATTLEFIELD, object_id=card.id)
  Death       -> destroy via game.destroy(card.id) (moves to graveyard first,
                 then emits OBJECT_DESTROYED for the death trigger filter).
  Attack      -> ATTACK_DECLARED(attacker_id=card.id)
  End-step    -> PHASE_START(phase=END_STEP)
  Upkeep      -> PHASE_START(phase=UPKEEP)
  Damage      -> DAMAGE event with source=card.id
  Tap         -> TAPPED event for card.id
  Spell cast  -> SPELL_CAST event by controller
  Life gain   -> LIFE_CHANGE(amount=+1) for controller
  Activated   -> register interceptor only (manual-mode activation)
  Static      -> register interceptor only (no event to fire; existence test)

Run: PYTHONPATH=. python tests/test_lci_interceptors.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine import (  # noqa: E402
    Game, Event, EventType, ZoneType, CardType,
)
from src.cards.lost_caverns_ixalan import LOST_CAVERNS_IXALAN_CARDS  # noqa: E402

# Cards we deliberately do not test - reason listed.
SKIPPED_CARDS: dict[str, str] = {
    # Modal / target-choice / replacement effects that require human input
    # or multi-card setup beyond the scope of single-card trigger validation.
    "Modal/target-choice/replacement cards are handled by test_lci_rulings.py": "out of scope",
}

# ---------------------------------------------------------------------------
# Scaffolding helpers
# ---------------------------------------------------------------------------


def _make_game() -> Game:
    """Two-player vanilla MTG game with library zones populated AND a small
    amount of common context (extra creatures on both sides, cards in hand,
    permanents in graveyard) so cards whose triggers are conditional on
    "you control a Vampire / opponent has a card in hand / graveyard has 4+
    permanents" have something to react to."""
    from src.engine.types import Characteristics, GameObject, ObjectState
    g = Game()
    g.add_player("p1")
    g.add_player("p2")
    # Add a vanilla 2/2 creature for each player so "creatures you control"
    # / "creatures opponent controls" filters pass.
    for owner in ("p1", "p2"):
        for tribe in ("Vampire", "Pirate", "Dinosaur", "Merfolk"):
            ctx = g.create_object(
                name=f"Test {tribe} {owner}",
                owner_id=owner,
                zone=ZoneType.BATTLEFIELD,
                characteristics=Characteristics(
                    types={CardType.CREATURE},
                    subtypes={tribe},
                    power=2,
                    toughness=2,
                ),
                card_def=None,
            )
            ctx.state.summoning_sickness = False
        # Toss a dummy permanent card into the graveyard for Descend.
        for _ in range(4):
            gy_obj = g.create_object(
                name=f"Test GY {owner}",
                owner_id=owner,
                zone=ZoneType.GRAVEYARD,
                characteristics=Characteristics(types={CardType.CREATURE}),
                card_def=None,
            )
        # Put a token card in the hand zone so "look at opponent's hand"
        # triggers see something.
        hand_obj = g.create_object(
            name=f"Test Hand {owner}",
            owner_id=owner,
            zone=ZoneType.HAND,
            characteristics=Characteristics(types={CardType.SORCERY}),
            card_def=None,
        )
    return g


def _place(game: Game, owner_id: str, card_def) -> "GameObject":
    """Drop a card onto the battlefield directly. setup_interceptors runs
    because create_object triggers it for BATTLEFIELD zone."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    # Make sure no summoning sickness for attack-trigger tests.
    obj.state.summoning_sickness = False
    obj.state.tapped = False
    return obj


def _emitted_event_types(events) -> list[str]:
    return [e.type.name for e in events]


def _has_observable_effect(events, state_before, state_after) -> bool:
    """An effect is observable if the trigger emitted ANY new events
    OR if a PendingChoice is now open on the state."""
    if events:
        return True
    if state_after.pending_choice is not None and state_before is None:
        return True
    return False


def _fire_etb(game, obj):
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "to_zone_type": ZoneType.BATTLEFIELD,
            "from_zone_type": ZoneType.HAND,
            "to_zone": "battlefield",
            "from_zone": f"hand_{obj.controller}",
        },
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_attack(game, obj):
    obj.state.attacking = True
    obj.state.summoning_sickness = False
    return game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker_id": obj.id},
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_death(game, obj):
    """Move to graveyard then emit OBJECT_DESTROYED matching make_death_trigger's
    default filter, which requires obj.zone == GRAVEYARD at trigger time."""
    bf_zone = game.state.zones.get("battlefield")
    if bf_zone and obj.id in bf_zone.objects:
        bf_zone.objects.remove(obj.id)
    gy_key = f"graveyard_{obj.controller}"
    gy_zone = game.state.zones.get(gy_key)
    if gy_zone is None:
        # ensure graveyard exists
        from src.engine.types import Zone
        gy_zone = Zone(type=ZoneType.GRAVEYARD, owner=obj.controller)
        game.state.zones[gy_key] = gy_zone
    if obj.id not in gy_zone.objects:
        gy_zone.objects.append(obj.id)
    obj.zone = ZoneType.GRAVEYARD
    return game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": obj.id},
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_phase(game, phase_name: str, player_id: str):
    # Pre-populate common turn_data flags so conditional end_step / upkeep
    # triggers have a reason to fire.
    td = game.state.turn_data
    td.setdefault(f"life_gained_{player_id}", 10)
    td.setdefault(f"descended_{player_id}", True)
    td.setdefault(f"creatures_played_{player_id}", 3)
    td.setdefault(f"spells_cast_{player_id}", 3)
    td.setdefault(f"discover_count_{player_id}", 1)
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={"phase": phase_name, "player": player_id},
        source=None,
        controller=player_id,
    ))


def _fire_damage(game, obj, target_id):
    return game.emit(Event(
        type=EventType.DAMAGE,
        payload={"source": obj.id, "target": target_id, "amount": 1},
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_tap(game, obj):
    obj.state.tapped = True
    return game.emit(Event(
        type=EventType.TAP,
        payload={"object_id": obj.id},
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_spell_cast(game, controller_id: str):
    return game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={"controller": controller_id},
        source=None,
        controller=controller_id,
    ))


def _fire_life_gain(game, controller_id: str):
    return game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={"player": controller_id, "amount": 1, "reason": "gain"},
        source=None,
        controller=controller_id,
    ))


def _assert_fires_observably(events, state_after, card_name: str):
    """Trigger should produce SOMETHING - events, a choice, or state mutation."""
    if events:
        return  # any event emitted (including the firing event itself) counts as activity
    if state_after.pending_choice is not None:
        return
    raise AssertionError(
        f"{card_name}: interceptor fired but emitted no events and opened no choice"
    )


def _assert_emits_extra(events, fire_event_type, card_name: str, state=None):
    """Stricter assert: at least one event beyond the firing event itself,
    OR a PendingChoice opened (target-choice cards open a UI prompt).
    Failures here represent the depths-trap pattern: trigger fires but
    effect_fn returns [] with no condition or no choice opened.
    """
    extras = [e for e in events if e.type != fire_event_type]
    if extras:
        return
    if state is not None and getattr(state, "pending_choice", None) is not None:
        return
    raise AssertionError(
        f"{card_name}: trigger fired ({fire_event_type.name}) but produced no "
        f"downstream events and opened no PendingChoice (depths trap?)"
    )

def test_waylaying_pirates():
    """Waylaying Pirates: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Waylaying Pirates"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Waylaying Pirates", game.state)

def test_forgotten_monument():
    """Forgotten Monument: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Forgotten Monument"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Forgotten Monument", game.state)

def test_tinker_s_tote():
    """Tinker's Tote: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Tinker's Tote"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Tinker's Tote", game.state)

def test_deep_cavern_bat():
    """Deep-Cavern Bat: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Deep-Cavern Bat"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Deep-Cavern Bat", game.state)

def test_ghalta_stampede_tyrant():
    """Ghalta, Stampede Tyrant: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Ghalta, Stampede Tyrant"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Ghalta, Stampede Tyrant", game.state)

def test_fabrication_foundry():
    """Fabrication Foundry: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Fabrication Foundry"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Fabrication Foundry", game.state)

def test_ironpaw_aspirant():
    """Ironpaw Aspirant: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Ironpaw Aspirant"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Ironpaw Aspirant", game.state)

def test_quintorius_kand():
    """Quintorius Kand: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Quintorius Kand"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Quintorius Kand", game.state)

def test_magmatic_galleon():
    """Magmatic Galleon: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Magmatic Galleon"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Magmatic Galleon", game.state)

def test_malamet_war_scribe():
    """Malamet War Scribe: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Malamet War Scribe"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Malamet War Scribe", game.state)

def test_chupacabra_echo():
    """Chupacabra Echo: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Chupacabra Echo"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Chupacabra Echo", game.state)

def test_sunshot_militia():
    """Sunshot Militia: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sunshot Militia"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Sunshot Militia", game.state)

def test_glorifier_of_suffering():
    """Glorifier of Suffering: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Glorifier of Suffering"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Glorifier of Suffering", game.state)

def test_geological_appraiser():
    """Geological Appraiser: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Geological Appraiser"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Geological Appraiser", game.state)

def test_kitesail_larcenist():
    """Kitesail Larcenist: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Kitesail Larcenist"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Kitesail Larcenist", game.state)

def test_dusk_rose_reliquary():
    """Dusk Rose Reliquary: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Dusk Rose Reliquary"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Dusk Rose Reliquary", game.state)

def test_kutzil_s_flanker():
    """Kutzil's Flanker: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Kutzil's Flanker"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Kutzil's Flanker", game.state)

def test_skullcap_snail():
    """Skullcap Snail: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Skullcap Snail"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Skullcap Snail", game.state)

def test_queen_s_bay_paladin():
    """Queen's Bay Paladin: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Queen's Bay Paladin"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Queen's Bay Paladin", game.state)

def test_guardian_of_the_great_door():
    """Guardian of the Great Door: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Guardian of the Great Door"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Guardian of the Great Door", game.state)

def test_orazca_puzzle_door():
    """Orazca Puzzle-Door: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Orazca Puzzle-Door"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Orazca Puzzle-Door", game.state)

def test_cartographer_s_companion():
    """Cartographer's Companion: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Cartographer's Companion"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Cartographer's Companion", game.state)

def test_plundering_pirate():
    """Plundering Pirate: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Plundering Pirate"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Plundering Pirate", game.state)

def test_rampaging_spiketail():
    """Rampaging Spiketail: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Rampaging Spiketail"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Rampaging Spiketail", game.state)

def test_runaway_boulder():
    """Runaway Boulder: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Runaway Boulder"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Runaway Boulder", game.state)

def test_seismic_monstrosaur():
    """Seismic Monstrosaur: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Seismic Monstrosaur"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Seismic Monstrosaur", game.state)

def test_oltec_cloud_guard():
    """Oltec Cloud Guard: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Oltec Cloud Guard"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Oltec Cloud Guard", game.state)

def test_marauding_brinefang():
    """Marauding Brinefang: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Marauding Brinefang"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Marauding Brinefang", game.state)

def test_coati_scavenger():
    """Coati Scavenger: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Coati Scavenger"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Coati Scavenger", game.state)

def test_tendril_of_the_mycotyrant():
    """Tendril of the Mycotyrant: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Tendril of the Mycotyrant"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Tendril of the Mycotyrant", game.state)

def test_scampering_surveyor():
    """Scampering Surveyor: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Scampering Surveyor"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Scampering Surveyor", game.state)

def test_captain_storm_cosmium_raider():
    """Captain Storm, Cosmium Raider: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Captain Storm, Cosmium Raider"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Captain Storm, Cosmium Raider", game.state)

def test_sunfire_torch():
    """Sunfire Torch: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sunfire Torch"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Sunfire Torch", game.state)

def test_sentinel_of_the_nameless_city():
    """Sentinel of the Nameless City: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sentinel of the Nameless City"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Sentinel of the Nameless City", game.state)

def test_pit_of_offerings():
    """Pit of Offerings: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Pit of Offerings"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Pit of Offerings", game.state)

def test_echoing_deeps():
    """Echoing Deeps: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Echoing Deeps"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Echoing Deeps", game.state)

def test_thrashing_brontodon():
    """Thrashing Brontodon: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Thrashing Brontodon"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Thrashing Brontodon", game.state)

def test_envoy_of_okinec_ahau():
    """Envoy of Okinec Ahau: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Envoy of Okinec Ahau"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Envoy of Okinec Ahau", game.state)

def test_rampaging_ceratops():
    """Rampaging Ceratops: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Rampaging Ceratops"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Rampaging Ceratops", game.state)

def test_sanguine_evangelist():
    """Sanguine Evangelist: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sanguine Evangelist"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Sanguine Evangelist", game.state)

def test_spyglass_siren():
    """Spyglass Siren: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Spyglass Siren"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Spyglass Siren", game.state)

def test_uchbenbak_the_great_mistake():
    """Uchbenbak, the Great Mistake: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Uchbenbak, the Great Mistake"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Uchbenbak, the Great Mistake", game.state)

def test_soaring_sandwing():
    """Soaring Sandwing: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Soaring Sandwing"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Soaring Sandwing", game.state)

def test_panicked_altisaur():
    """Panicked Altisaur: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Panicked Altisaur"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Panicked Altisaur", game.state)

def test_abuelo_ancestral_echo():
    """Abuelo, Ancestral Echo: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Abuelo, Ancestral Echo"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Abuelo, Ancestral Echo", game.state)

def test_river_herald_guide():
    """River Herald Guide: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["River Herald Guide"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "River Herald Guide", game.state)

def test_tishana_s_tidebinder():
    """Tishana's Tidebinder: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Tishana's Tidebinder"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Tishana's Tidebinder", game.state)

def test_jadelight_spelunker():
    """Jadelight Spelunker: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Jadelight Spelunker"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Jadelight Spelunker", game.state)

def test_council_of_echoes():
    """Council of Echoes: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Council of Echoes"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Council of Echoes", game.state)

def test_mischievous_pup():
    """Mischievous Pup: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Mischievous Pup"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Mischievous Pup", game.state)

def test_poison_dart_frog():
    """Poison Dart Frog: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Poison Dart Frog"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Poison Dart Frog", game.state)

def test_spelunking():
    """Spelunking: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Spelunking"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Spelunking", game.state)

def test_didact_echo():
    """Didact Echo: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Didact Echo"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Didact Echo", game.state)

def test_corpses_of_the_lost():
    """Corpses of the Lost: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Corpses of the Lost"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Corpses of the Lost", game.state)

def test_threefold_thunderhulk():
    """Threefold Thunderhulk: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Threefold Thunderhulk"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Threefold Thunderhulk", game.state)

def test_kutzil_malamet_exemplar():
    """Kutzil, Malamet Exemplar: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Kutzil, Malamet Exemplar"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Kutzil, Malamet Exemplar", game.state)

def test_saheeli_the_sun_s_brilliance():
    """Saheeli, the Sun's Brilliance: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Saheeli, the Sun's Brilliance"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Saheeli, the Sun's Brilliance", game.state)

def test_seeker_of_sunlight():
    """Seeker of Sunlight: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Seeker of Sunlight"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Seeker of Sunlight", game.state)

def test_hermitic_nautilus():
    """Hermitic Nautilus: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Hermitic Nautilus"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Hermitic Nautilus", game.state)

def test_etali_s_favor():
    """Etali's Favor: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Etali's Favor"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Etali's Favor", game.state)

def test_itzquinth_firstborn_of_gishath():
    """Itzquinth, Firstborn of Gishath: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Itzquinth, Firstborn of Gishath"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Itzquinth, Firstborn of Gishath", game.state)

def test_waterwind_scout():
    """Waterwind Scout: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Waterwind Scout"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Waterwind Scout", game.state)

def test_vito_s_inquisitor():
    """Vito's Inquisitor: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Vito's Inquisitor"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Vito's Inquisitor", game.state)

def test_intrepid_paleontologist():
    """Intrepid Paleontologist: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Intrepid Paleontologist"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Intrepid Paleontologist", game.state)

def test_goldfury_strider():
    """Goldfury Strider: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Goldfury Strider"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Goldfury Strider", game.state)

def test_oaken_siren():
    """Oaken Siren: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Oaken Siren"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Oaken Siren", game.state)

def test_bedrock_tortoise():
    """Bedrock Tortoise: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Bedrock Tortoise"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Bedrock Tortoise", game.state)

def test_promising_vein():
    """Promising Vein: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Promising Vein"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Promising Vein", game.state)

def test_earthshaker_dreadmaw():
    """Earthshaker Dreadmaw: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Earthshaker Dreadmaw"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Earthshaker Dreadmaw", game.state)

def test_pathfinding_axejaw():
    """Pathfinding Axejaw: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Pathfinding Axejaw"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Pathfinding Axejaw", game.state)

def test_palani_s_hatcher():
    """Palani's Hatcher: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Palani's Hatcher"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Palani's Hatcher", game.state)

def test_bloodthorn_flail():
    """Bloodthorn Flail: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Bloodthorn Flail"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Bloodthorn Flail", game.state)

def test_deathcap_marionette():
    """Deathcap Marionette: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Deathcap Marionette"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Deathcap Marionette", game.state)

def test_souls_of_the_lost():
    """Souls of the Lost: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Souls of the Lost"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Souls of the Lost", game.state)

def test_malamet_scythe():
    """Malamet Scythe: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Malamet Scythe"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Malamet Scythe", game.state)

def test_song_of_stupefaction():
    """Song of Stupefaction: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Song of Stupefaction"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Song of Stupefaction", game.state)

def test_starving_revenant():
    """Starving Revenant: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Starving Revenant"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Starving Revenant", game.state)

def test_sage_of_days():
    """Sage of Days: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sage of Days"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Sage of Days", game.state)

def test_pirate_hat():
    """Pirate Hat: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Pirate Hat"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Pirate Hat", game.state)

def test_warden_of_the_inner_sky():
    """Warden of the Inner Sky: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Warden of the Inner Sky"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Warden of the Inner Sky", game.state)

def test_mineshaft_spider():
    """Mineshaft Spider: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Mineshaft Spider"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Mineshaft Spider", game.state)

def test_sunken_citadel():
    """Sunken Citadel: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sunken Citadel"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Sunken Citadel", game.state)

def test_staunch_crewmate():
    """Staunch Crewmate: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Staunch Crewmate"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Staunch Crewmate", game.state)

def test_compass_gnome():
    """Compass Gnome: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Compass Gnome"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Compass Gnome", game.state)

def test_captivating_cave():
    """Captivating Cave: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Captivating Cave"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Captivating Cave", game.state)

def test_river_herald_scout():
    """River Herald Scout: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["River Herald Scout"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "River Herald Scout", game.state)

def test_hotfoot_gnome():
    """Hotfoot Gnome: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Hotfoot Gnome"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Hotfoot Gnome", game.state)

def test_kinjalli_s_dawnrunner():
    """Kinjalli's Dawnrunner: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Kinjalli's Dawnrunner"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Kinjalli's Dawnrunner", game.state)

def test_sorcerous_spyglass():
    """Sorcerous Spyglass: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sorcerous Spyglass"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Sorcerous Spyglass", game.state)

def test_cavernous_maw():
    """Cavernous Maw: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Cavernous Maw"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Cavernous Maw", game.state)

def test_the_ancient_one():
    """The Ancient One: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["The Ancient One"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "The Ancient One", game.state)

def test_cenote_scout():
    """Cenote Scout: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Cenote Scout"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Cenote Scout", game.state)

def test_clay_fired_bricks():
    """Clay-Fired Bricks: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Clay-Fired Bricks"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Clay-Fired Bricks", game.state)

def test_abyssal_gorestalker():
    """Abyssal Gorestalker: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Abyssal Gorestalker"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Abyssal Gorestalker", game.state)

def test_vanguard_of_the_rose():
    """Vanguard of the Rose: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Vanguard of the Rose"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Vanguard of the Rose", game.state)

def test_acolyte_of_aclazotz():
    """Acolyte of Aclazotz: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Acolyte of Aclazotz"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Acolyte of Aclazotz", game.state)

def test_cogwork_wrestler():
    """Cogwork Wrestler: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Cogwork Wrestler"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Cogwork Wrestler", game.state)

def test_buried_treasure():
    """Buried Treasure: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Buried Treasure"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Buried Treasure", game.state)

def test_glowcap_lantern():
    """Glowcap Lantern: ETB trigger. style=etb, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Glowcap Lantern"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Glowcap Lantern", game.state)

def test_mephitic_draught():
    """Mephitic Draught: ETB trigger. style=etb, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Mephitic Draught"]
    obj = _place(game, "p1", card_def)
    events = _fire_etb(game, obj)
    _assert_emits_extra(events, EventType.ZONE_CHANGE, "Mephitic Draught", game.state)

def test_attentive_sunscribe():
    """Attentive Sunscribe: Tap trigger. style=tap, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Attentive Sunscribe"]
    obj = _place(game, "p1", card_def)
    events = _fire_tap(game, obj)
    _assert_emits_extra(events, EventType.TAP, "Attentive Sunscribe", game.state)

def test_volatile_wanderglyph():
    """Volatile Wanderglyph: Tap trigger. style=tap, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Volatile Wanderglyph"]
    obj = _place(game, "p1", card_def)
    events = _fire_tap(game, obj)
    _assert_emits_extra(events, EventType.TAP, "Volatile Wanderglyph", game.state)

def test_market_gnome():
    """Market Gnome: Death trigger. style=death, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Market Gnome"]
    obj = _place(game, "p1", card_def)
    events = _fire_death(game, obj)
    _assert_emits_extra(events, EventType.OBJECT_DESTROYED, "Market Gnome", game.state)

def test_miner_s_guidewing():
    """Miner's Guidewing: Death trigger. style=death, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Miner's Guidewing"]
    obj = _place(game, "p1", card_def)
    events = _fire_death(game, obj)
    _assert_emits_extra(events, EventType.OBJECT_DESTROYED, "Miner's Guidewing", game.state)

def test_zoetic_glyph():
    """Zoetic Glyph: Death trigger. style=death, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Zoetic Glyph"]
    obj = _place(game, "p1", card_def)
    events = _fire_death(game, obj)
    _assert_emits_extra(events, EventType.OBJECT_DESTROYED, "Zoetic Glyph", game.state)

def test_greedy_freebooter():
    """Greedy Freebooter: Death trigger. style=death, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Greedy Freebooter"]
    obj = _place(game, "p1", card_def)
    events = _fire_death(game, obj)
    _assert_emits_extra(events, EventType.OBJECT_DESTROYED, "Greedy Freebooter", game.state)

def test_primordial_gnawer():
    """Primordial Gnawer: Death trigger. style=death, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Primordial Gnawer"]
    obj = _place(game, "p1", card_def)
    events = _fire_death(game, obj)
    _assert_emits_extra(events, EventType.OBJECT_DESTROYED, "Primordial Gnawer", game.state)

def test_synapse_necromage():
    """Synapse Necromage: Death trigger. style=death, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Synapse Necromage"]
    obj = _place(game, "p1", card_def)
    events = _fire_death(game, obj)
    _assert_emits_extra(events, EventType.OBJECT_DESTROYED, "Synapse Necromage", game.state)

def test_digsite_conservator():
    """Digsite Conservator: Death trigger. style=death, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Digsite Conservator"]
    obj = _place(game, "p1", card_def)
    events = _fire_death(game, obj)
    _assert_emits_extra(events, EventType.OBJECT_DESTROYED, "Digsite Conservator", game.state)

def test_resplendent_angel():
    """Resplendent Angel: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Resplendent Angel"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Resplendent Angel", game.state)

def test_ruin_lurker_bat():
    """Ruin-Lurker Bat: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Ruin-Lurker Bat"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Ruin-Lurker Bat", game.state)

def test_akal_pakal_first_among_equals():
    """Akal Pakal, First Among Equals: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Akal Pakal, First Among Equals"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Akal Pakal, First Among Equals", game.state)

def test_broodrage_mycoid():
    """Broodrage Mycoid: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Broodrage Mycoid"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Broodrage Mycoid", game.state)

def test_canonized_in_blood():
    """Canonized in Blood: End-step trigger. style=end_step, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Canonized in Blood"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Canonized in Blood", game.state)

def test_deep_goblin_skulltaker():
    """Deep Goblin Skulltaker: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Deep Goblin Skulltaker"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Deep Goblin Skulltaker", game.state)

def test_stalactite_stalker():
    """Stalactite Stalker: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Stalactite Stalker"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Stalactite Stalker", game.state)

def test_child_of_the_volcano():
    """Child of the Volcano: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Child of the Volcano"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Child of the Volcano", game.state)

def test_enterprising_scallywag():
    """Enterprising Scallywag: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Enterprising Scallywag"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Enterprising Scallywag", game.state)

def test_the_mycotyrant():
    """The Mycotyrant: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["The Mycotyrant"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "The Mycotyrant", game.state)

def test_zoyowa_lava_tongue():
    """Zoyowa Lava-Tongue: End-step trigger. style=end_step, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Zoyowa Lava-Tongue"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Zoyowa Lava-Tongue", game.state)

def test_chimil_the_inner_sun():
    """Chimil, the Inner Sun: End-step trigger. style=end_step, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Chimil, the Inner Sun"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "end_step", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Chimil, the Inner Sun", game.state)

def test_restless_anchorage():
    """Restless Anchorage: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Restless Anchorage"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Restless Anchorage", game.state)

def test_caparocti_sunborn():
    """Caparocti Sunborn: Attack trigger. style=attack, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Caparocti Sunborn"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Caparocti Sunborn", game.state)

def test_preacher_of_the_schism():
    """Preacher of the Schism: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Preacher of the Schism"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Preacher of the Schism", game.state)

def test_restless_reef():
    """Restless Reef: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Restless Reef"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Restless Reef", game.state)

def test_inti_seneschal_of_the_sun():
    """Inti, Seneschal of the Sun: Attack trigger. style=attack, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Inti, Seneschal of the Sun"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Inti, Seneschal of the Sun", game.state)

def test_sovereign_okinec_ahau():
    """Sovereign Okinec Ahau: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Sovereign Okinec Ahau"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Sovereign Okinec Ahau", game.state)

def test_restless_prairie():
    """Restless Prairie: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Restless Prairie"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Restless Prairie", game.state)

def test_subterranean_schooner():
    """Subterranean Schooner: Attack trigger. style=attack, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Subterranean Schooner"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Subterranean Schooner", game.state)

def test_pugnacious_hammerskull():
    """Pugnacious Hammerskull: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Pugnacious Hammerskull"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Pugnacious Hammerskull", game.state)

def test_restless_ridgeline():
    """Restless Ridgeline: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Restless Ridgeline"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Restless Ridgeline", game.state)

def test_stinging_cave_crawler():
    """Stinging Cave Crawler: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Stinging Cave Crawler"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Stinging Cave Crawler", game.state)

def test_malamet_veteran():
    """Malamet Veteran: Attack trigger. style=attack, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Malamet Veteran"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Malamet Veteran", game.state)

def test_malamet_brawler():
    """Malamet Brawler: Attack trigger. style=attack, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Malamet Brawler"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Malamet Brawler", game.state)

def test_burning_sun_cavalry():
    """Burning Sun Cavalry: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Burning Sun Cavalry"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Burning Sun Cavalry", game.state)

def test_anim_pakal_thousandth_moon():
    """Anim Pakal, Thousandth Moon: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Anim Pakal, Thousandth Moon"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Anim Pakal, Thousandth Moon", game.state)

def test_breeches_eager_pillager():
    """Breeches, Eager Pillager: Attack trigger. style=attack, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Breeches, Eager Pillager"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Breeches, Eager Pillager", game.state)

def test_brazen_blademaster():
    """Brazen Blademaster: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Brazen Blademaster"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Brazen Blademaster", game.state)

def test_careening_mine_cart():
    """Careening Mine Cart: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Careening Mine Cart"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Careening Mine Cart", game.state)

def test_thousand_moons_crackshot():
    """Thousand Moons Crackshot: Attack trigger. style=attack, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Thousand Moons Crackshot"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Thousand Moons Crackshot", game.state)

def test_screaming_phantom():
    """Screaming Phantom: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Screaming Phantom"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Screaming Phantom", game.state)

def test_disruptor_wanderglyph():
    """Disruptor Wanderglyph: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Disruptor Wanderglyph"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Disruptor Wanderglyph", game.state)

def test_restless_vents():
    """Restless Vents: Attack trigger. style=attack, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Restless Vents"]
    obj = _place(game, "p1", card_def)
    events = _fire_attack(game, obj)
    _assert_emits_extra(events, EventType.ATTACK_DECLARED, "Restless Vents", game.state)

def test_frilled_cave_wurm():
    """Frilled Cave-Wurm: Static interceptor. style=static, classification=static_or_grant.
    Confirms setup_interceptors registered at least one interceptor on the object."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Frilled Cave-Wurm"]
    obj = _place(game, "p1", card_def)
    interceptor_ids = obj.interceptor_ids or []
    if not interceptor_ids:
        # Some static helpers register cost-reduction / pt-boost differently.
        # Accept if any interceptor in the game's pipeline lists this obj as source.
        any_from = any(
            i.source == obj.id for i in game.state.interceptors.values()
        ) if hasattr(game.state, "interceptors") else False
        if not any_from:
            raise AssertionError(
                f"Frilled Cave-Wurm: setup_interceptors registered nothing"
            )

def test_echo_of_dusk():
    """Echo of Dusk: Static interceptor. style=static, classification=static_or_grant.
    Confirms setup_interceptors registered at least one interceptor on the object."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Echo of Dusk"]
    obj = _place(game, "p1", card_def)
    interceptor_ids = obj.interceptor_ids or []
    if not interceptor_ids:
        # Some static helpers register cost-reduction / pt-boost differently.
        # Accept if any interceptor in the game's pipeline lists this obj as source.
        any_from = any(
            i.source == obj.id for i in game.state.interceptors.values()
        ) if hasattr(game.state, "interceptors") else False
        if not any_from:
            raise AssertionError(
                f"Echo of Dusk: setup_interceptors registered nothing"
            )

def test_gargantuan_leech():
    """Gargantuan Leech: Static interceptor. style=static, classification=static_or_grant.
    Confirms setup_interceptors registered at least one interceptor on the object."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Gargantuan Leech"]
    obj = _place(game, "p1", card_def)
    interceptor_ids = obj.interceptor_ids or []
    if not interceptor_ids:
        # Some static helpers register cost-reduction / pt-boost differently.
        # Accept if any interceptor in the game's pipeline lists this obj as source.
        any_from = any(
            i.source == obj.id for i in game.state.interceptors.values()
        ) if hasattr(game.state, "interceptors") else False
        if not any_from:
            raise AssertionError(
                f"Gargantuan Leech: setup_interceptors registered nothing"
            )

def test_goblin_tomb_raider():
    """Goblin Tomb Raider: Static interceptor. style=static, classification=static_or_grant.
    Confirms setup_interceptors registered at least one interceptor on the object."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Goblin Tomb Raider"]
    obj = _place(game, "p1", card_def)
    interceptor_ids = obj.interceptor_ids or []
    if not interceptor_ids:
        # Some static helpers register cost-reduction / pt-boost differently.
        # Accept if any interceptor in the game's pipeline lists this obj as source.
        any_from = any(
            i.source == obj.id for i in game.state.interceptors.values()
        ) if hasattr(game.state, "interceptors") else False
        if not any_from:
            raise AssertionError(
                f"Goblin Tomb Raider: setup_interceptors registered nothing"
            )

def test_basking_capybara():
    """Basking Capybara: Static interceptor. style=static, classification=static_or_grant.
    Confirms setup_interceptors registered at least one interceptor on the object."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Basking Capybara"]
    obj = _place(game, "p1", card_def)
    interceptor_ids = obj.interceptor_ids or []
    if not interceptor_ids:
        # Some static helpers register cost-reduction / pt-boost differently.
        # Accept if any interceptor in the game's pipeline lists this obj as source.
        any_from = any(
            i.source == obj.id for i in game.state.interceptors.values()
        ) if hasattr(game.state, "interceptors") else False
        if not any_from:
            raise AssertionError(
                f"Basking Capybara: setup_interceptors registered nothing"
            )

def test_the_skullspore_nexus():
    """The Skullspore Nexus: Static interceptor. style=static, classification=static_or_grant.
    Confirms setup_interceptors registered at least one interceptor on the object."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["The Skullspore Nexus"]
    obj = _place(game, "p1", card_def)
    interceptor_ids = obj.interceptor_ids or []
    if not interceptor_ids:
        # Some static helpers register cost-reduction / pt-boost differently.
        # Accept if any interceptor in the game's pipeline lists this obj as source.
        any_from = any(
            i.source == obj.id for i in game.state.interceptors.values()
        ) if hasattr(game.state, "interceptors") else False
        if not any_from:
            raise AssertionError(
                f"The Skullspore Nexus: setup_interceptors registered nothing"
            )

def test_roaming_throne():
    """Roaming Throne: Static interceptor. style=static, classification=static_or_grant.
    Confirms setup_interceptors registered at least one interceptor on the object."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Roaming Throne"]
    obj = _place(game, "p1", card_def)
    interceptor_ids = obj.interceptor_ids or []
    if not interceptor_ids:
        # Some static helpers register cost-reduction / pt-boost differently.
        # Accept if any interceptor in the game's pipeline lists this obj as source.
        any_from = any(
            i.source == obj.id for i in game.state.interceptors.values()
        ) if hasattr(game.state, "interceptors") else False
        if not any_from:
            raise AssertionError(
                f"Roaming Throne: setup_interceptors registered nothing"
            )

def test_malcolm_alluring_scoundrel():
    """Malcolm, Alluring Scoundrel: Damage trigger. style=damage, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Malcolm, Alluring Scoundrel"]
    obj = _place(game, "p1", card_def)
    events = _fire_damage(game, obj, "p2")
    _assert_emits_extra(events, EventType.DAMAGE, "Malcolm, Alluring Scoundrel", game.state)

def test_gishath_sun_s_avatar():
    """Gishath, Sun's Avatar: Damage trigger. style=damage, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Gishath, Sun's Avatar"]
    obj = _place(game, "p1", card_def)
    events = _fire_damage(game, obj, "p2")
    _assert_emits_extra(events, EventType.DAMAGE, "Gishath, Sun's Avatar", game.state)

def test_contested_game_ball():
    """Contested Game Ball: Damage trigger. style=damage, classification=empty."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Contested Game Ball"]
    obj = _place(game, "p1", card_def)
    events = _fire_damage(game, obj, "p2")
    _assert_emits_extra(events, EventType.DAMAGE, "Contested Game Ball", game.state)

def test_bonehoard_dracosaur():
    """Bonehoard Dracosaur: Upkeep trigger. style=upkeep, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Bonehoard Dracosaur"]
    obj = _place(game, "p1", card_def)
    events = _fire_phase(game, "upkeep", "p1")
    _assert_emits_extra(events, EventType.PHASE_START, "Bonehoard Dracosaur", game.state)

def test_poetic_ingenuity():
    """Poetic Ingenuity: Spell-cast trigger. style=spell_cast, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Poetic Ingenuity"]
    obj = _place(game, "p1", card_def)
    events = _fire_spell_cast(game, "p1")
    _assert_emits_extra(events, EventType.SPELL_CAST, "Poetic Ingenuity", game.state)

def test_amalia_benavides_aguirre():
    """Amalia Benavides Aguirre: Life-gain trigger. style=life_gain, classification=emits."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Amalia Benavides Aguirre"]
    obj = _place(game, "p1", card_def)
    events = _fire_life_gain(game, "p1")
    _assert_emits_extra(events, EventType.LIFE_CHANGE, "Amalia Benavides Aguirre", game.state)

def test_hoverstone_pilgrim():
    """Hoverstone Pilgrim: Activated ability. style=activated, classification=emits.
    For activated abilities we just confirm setup_interceptors ran without error
    (since activation is manual-mode and requires UI/cost-pay)."""
    game = _make_game()
    card_def = LOST_CAVERNS_IXALAN_CARDS["Hoverstone Pilgrim"]
    obj = _place(game, "p1", card_def)
    # If we got here, setup_interceptors ran. Confirm at least one interceptor
    # got registered.
    interceptor_ids = obj.interceptor_ids or []
    activated_id = obj.state.activated_ability_ids if hasattr(obj.state, "activated_ability_ids") else []
    if not interceptor_ids and not activated_id:
        raise AssertionError(
            f"Hoverstone Pilgrim: setup_interceptors registered nothing (no interceptors, "
            f"no activated abilities)"
        )



# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed, failed, errors = [], [], []
    for name, fn in tests:
        try:
            fn()
            passed.append(name)
        except AssertionError as e:
            failed.append((name, str(e)))
        except Exception as e:
            errors.append((name, f"{type(e).__name__}: {e}", traceback.format_exc()))

    total = len(tests)
    print(f"\n=== LCI interceptor verification ===")
    print(f"  total:  {total}")
    print(f"  passed: {len(passed)}")
    print(f"  failed: {len(failed)}")
    print(f"  errors: {len(errors)}")
    pct = (100.0 * len(passed) / total) if total else 0.0
    print(f"  pass rate: {pct:.1f}%")
    if failed:
        print("\n--- FAILURES (depths-trap / empty effect_fn candidates) ---")
        for name, msg in failed:
            print(f"  {name}: {msg}")
    if errors:
        print("\n--- ERRORS (engine crashes / scaffolding bugs) ---")
        for name, msg, _tb in errors[:20]:
            print(f"  {name}: {msg}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
    sys.exit(0 if not failed and not errors else 1)
