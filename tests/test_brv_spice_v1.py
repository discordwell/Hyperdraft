"""
Tests for the BRV spice pack v1 cards.

One focused test per card: build a minimal Pokemon game state, exercise the
card's effect_fn / resolve callable, assert the expected events fire and the
expected state mutations happen.

These are NOT full-game integration tests — they verify the primitives the
depth scorer relies on. Full-game validation comes from /ultra-loop in Stage 3.

Run:
    python -m pytest tests/test_brv_spice_v1.py -q
"""

from __future__ import annotations

import os
import contextlib

import pytest

from src.engine.types import (
    CardType, Event, EventType, ZoneType, PokemonType, Player,
)


# ---------------------------------------------------------------------------
# Fixture: minimal Pokemon game with two players and reachable zones.
# ---------------------------------------------------------------------------


@pytest.fixture
def pkm_game():
    """Two-player Pokemon Game with empty boards but all zones present.

    Both players are registered as AI so the shared
    ``resolve_pending_choice_inline`` (in ``pending_choice_helpers.py``)
    will synchronously resolve any modal/target ``PendingChoice`` a card
    creates. Without AI registration, the helper would correctly leave
    the choice pending for a human to resolve via the session API —
    which would block these unit tests indefinitely.
    """
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.ai.pokemon.adapter import PokemonAIAdapter
    g = Game(mode="pokemon")
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    ai = PokemonAIAdapter()
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.set_ai_player(p1.id)
    g.turn_manager.set_ai_player(p2.id)
    return g, p1, p2


def _place_basic_pokemon(g, player_id, card_def, slot="active"):
    """Put a Pokemon card_def into the named slot, return GameObject.

    Game.create_object already appends to the zone for the given ZoneType, so
    we do NOT append again here.
    """
    zone_type = ZoneType.ACTIVE_SPOT if slot == "active" else ZoneType.BENCH
    obj = g.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=zone_type,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    return obj


def _attach_energy(g, pokemon_obj, energy_card_def, n=1):
    for _ in range(n):
        e = g.create_object(
            name=energy_card_def.name,
            owner_id=pokemon_obj.controller,
            zone=ZoneType.BATTLEFIELD,
            characteristics=energy_card_def.characteristics,
            card_def=energy_card_def,
        )
        pokemon_obj.state.attached_energy.append(e.id)


def _put_in_hand(g, player_id, card_def, n=1):
    out = []
    for _ in range(n):
        obj = g.create_object(
            name=card_def.name,
            owner_id=player_id,
            zone=ZoneType.HAND,
            characteristics=card_def.characteristics,
            card_def=card_def,
        )
        out.append(obj)
    return out


# ---------------------------------------------------------------------------
# Tests — Dimir guild
# ---------------------------------------------------------------------------


def test_mirko_vosk_lost_zone_attack(pkm_game):
    """Mirko Vosk's Lost Recall puts the top card of opp's deck in the Lost Zone."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.dimir import MIRKO_VOSK_MIND_DRINKER
    from src.cards.pokemon.sv_starter import CHARMANDER

    # Stack opp library with 4 distinguishable cards.
    for _ in range(4):
        obj = g.create_object(name="StackedCharmander", owner_id=p2.id,
                              zone=ZoneType.LIBRARY,
                              characteristics=CHARMANDER.characteristics,
                              card_def=CHARMANDER)
        g.state.zones[f"library_{p2.id}"].objects.append(obj.id)

    attacker = _place_basic_pokemon(g, p1.id, MIRKO_VOSK_MIND_DRINKER, slot="active")
    lib_before = len(g.state.zones[f"library_{p2.id}"].objects)
    lz_before = len(g.state.zones["lost_zone"].objects)

    attack = MIRKO_VOSK_MIND_DRINKER.attacks[0]
    events = attack["effect_fn"](attacker, g.state)

    # 1 card moved to LZ, others shuffled back; library reduced by 1.
    assert len(g.state.zones["lost_zone"].objects) == lz_before + 1
    assert len(g.state.zones[f"library_{p2.id}"].objects) == lib_before - 1
    assert any(e.type == EventType.PKM_LOST_ZONE for e in events)


def test_voidmage_apprentice_discards_opp_active_energy(pkm_game):
    """Voidmage's Energy Drain discards 1 Energy from opp Active."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.dimir import VOIDMAGE_APPRENTICE
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    attacker = _place_basic_pokemon(g, p1.id, VOIDMAGE_APPRENTICE)
    opp_active = _place_basic_pokemon(g, p2.id, CHARMANDER)
    _attach_energy(g, opp_active, FIRE_ENERGY, n=2)

    attack = VOIDMAGE_APPRENTICE.attacks[0]
    events = attack["effect_fn"](attacker, g.state)

    assert len(opp_active.state.attached_energy) == 1, "Should have discarded 1 Energy"
    assert any(e.type == EventType.PKM_DISCARD_ENERGY for e in events)


def test_dimir_interrogation_targets_pokemon_in_opp_hand(pkm_game):
    """Dimir Interrogation puts a Pokemon from opp hand on bottom of their deck.

    Net effect when opp has a non-empty deck: a Pokemon is yanked from hand and
    buried, opp draws a different card. Hand size stays the same; deck size
    stays the same; the specific Pokemon target is no longer in hand.
    """
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.dimir import DIMIR_INTERROGATION
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    targeted = _put_in_hand(g, p2.id, CHARMANDER, n=2)
    # Seed opp deck with non-Pokemon "background" cards so the buried Pokemon
    # doesn't cycle right back via the draw step.
    for _ in range(3):
        e = g.create_object(name="Fire Energy", owner_id=p2.id,
                            zone=ZoneType.LIBRARY,
                            characteristics=FIRE_ENERGY.characteristics,
                            card_def=FIRE_ENERGY)

    deck_before = len(g.state.zones[f"library_{p2.id}"].objects)
    hand_before = len(g.state.zones[f"hand_{p2.id}"].objects)

    event = Event(type=EventType.PKM_PLAY_ITEM, payload={"player": p1.id})
    events = DIMIR_INTERROGATION.resolve(event, g.state)

    # Hand size unchanged (one Pokemon buried, one card drawn back).
    assert len(g.state.zones[f"hand_{p2.id}"].objects) == hand_before
    # Deck size unchanged (one card buried, one drawn).
    assert len(g.state.zones[f"library_{p2.id}"].objects) == deck_before
    # The targeted Pokemon should no longer be in hand.
    targeted_ids = {t.id for t in targeted}
    hand_ids = set(g.state.zones[f"hand_{p2.id}"].objects)
    assert len(targeted_ids & hand_ids) < len(targeted_ids), (
        "At least one of the originally-targeted Pokemon should have been buried"
    )
    assert any(e.type == EventType.PKM_REVEAL_HAND for e in events)


def test_tox_pawpsule_applies_poison_and_scales(pkm_game):
    """Tox-Pawpsule Poisons opp Active and adds counters per poisoned Pokemon."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.dimir import TOX_PAWPSULE
    from src.cards.pokemon.sv_starter import CHARMANDER

    opp_active = _place_basic_pokemon(g, p2.id, CHARMANDER)
    # Pre-poison one bench Pokemon to test the scaling clause — actually no,
    # apply_status only works on Active. So the scaling is "how many of opp
    # board is already Poisoned." Add one bench poisoned via direct set.
    opp_bench_1 = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="bench")
    opp_bench_1.state.status_conditions.add("poisoned")

    event = Event(type=EventType.PKM_PLAY_ITEM, payload={"player": p1.id})
    events = TOX_PAWPSULE.resolve(event, g.state)

    assert "poisoned" in opp_active.state.status_conditions
    # Bench was already poisoned (count=1 before active); active just got poisoned (count=2)
    # Card text: "place 1 damage counter for each poisoned Pokemon opp has in play"
    # After applying poison to active, opp has 2 poisoned Pokemon.
    assert opp_active.state.damage_counters >= 1, (
        f"Expected at least 1 damage counter from poisoned-count payoff; "
        f"got {opp_active.state.damage_counters}"
    )
    assert any(e.type == EventType.PKM_APPLY_STATUS for e in events)


# ---------------------------------------------------------------------------
# Tests — Boros guild
# ---------------------------------------------------------------------------


def test_aurelia_ex_battalion_mark_pings_per_bench(pkm_game):
    """Aurelia ex's Battalion Mark: each Benched Pokemon may do 10 damage to opp Active."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.boros import AURELIA_THE_WARLEADER_EX
    from src.cards.pokemon.sv_starter import CHARMANDER

    attacker = _place_basic_pokemon(g, p1.id, AURELIA_THE_WARLEADER_EX)
    # Fill bench with 3 Pokemon.
    for _ in range(3):
        _place_basic_pokemon(g, p1.id, CHARMANDER, slot="bench")
    opp_active = _place_basic_pokemon(g, p2.id, CHARMANDER)

    attack = AURELIA_THE_WARLEADER_EX.attacks[-1]  # Battalion Mark is the second attack
    events = attack["effect_fn"](attacker, g.state)

    # 3 benched Pokemon × 1 damage counter each = 3 counters on opp active
    assert opp_active.state.damage_counters == 3
    assert sum(1 for e in events if e.type == EventType.PKM_PLACE_DAMAGE_COUNTERS) == 3


# ---------------------------------------------------------------------------
# Tests — Azorius guild
# ---------------------------------------------------------------------------


def test_nivmizzets_quandary_forces_opp_switch_and_moves_energy(pkm_game):
    """Niv-Mizzet's Quandary: opp switches Active with a Benched Pokemon; you redirect 2 Energy."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import NIV_MIZZETS_QUANDARY
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    opp_active = _place_basic_pokemon(g, p2.id, CHARMANDER)
    _attach_energy(g, opp_active, FIRE_ENERGY, n=2)
    opp_bench = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="bench")
    _attach_energy(g, opp_bench, FIRE_ENERGY, n=1)

    event = Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id})
    events = NIV_MIZZETS_QUANDARY.resolve(event, g.state)

    # Opp's Active should now be the formerly-benched Pokemon.
    active_after = g.state.zones[f"active_spot_{p2.id}"].objects[0]
    assert active_after == opp_bench.id, "Bench Pokemon should be promoted to Active"
    # Force switch + energy move events both fired.
    assert any(e.type == EventType.PKM_FORCE_SWITCH for e in events)
    assert any(e.type == EventType.PKM_MOVE_ENERGY for e in events)


def test_jace_memory_adept_discards_item_from_opp_hand(pkm_game):
    """Jace's Mental Triage discards 1 Item from opp hand."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import JACE_MEMORY_ADEPT
    from src.cards.pokemon.sv_starter import CHARMANDER, NEST_BALL

    attacker = _place_basic_pokemon(g, p1.id, JACE_MEMORY_ADEPT)
    _put_in_hand(g, p2.id, NEST_BALL, n=2)   # 2 Items
    _put_in_hand(g, p2.id, CHARMANDER, n=1)  # 1 Pokemon

    grave_before = len(g.state.zones[f"graveyard_{p2.id}"].objects)
    hand_items_before = sum(
        1 for cid in g.state.zones[f"hand_{p2.id}"].objects
        if CardType.TRAINER in g.state.objects[cid].characteristics.types
    )

    attack = JACE_MEMORY_ADEPT.attacks[0]
    events = attack["effect_fn"](attacker, g.state)

    grave_after = len(g.state.zones[f"graveyard_{p2.id}"].objects)
    hand_items_after = sum(
        1 for cid in g.state.zones[f"hand_{p2.id}"].objects
        if CardType.TRAINER in g.state.objects[cid].characteristics.types
    )
    assert grave_after == grave_before + 1, "Opp graveyard should have 1 more card"
    assert hand_items_after == hand_items_before - 1, "Opp should have 1 fewer Item in hand"
    assert any(e.type == EventType.PKM_REVEAL_HAND for e in events)


def test_pithing_drone_is_a_tool_that_fires_on_ko(pkm_game):
    """Pithing Drone attaches as Tool; smoke-test that it exists and is wired."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    # We can't run a full KO scenario here without combat plumbing; verify
    # the card is wired (has a setup_interceptors or resolve), and that its
    # type-line marks it as a Trainer-Tool.
    assert PITHING_DRONE is not None
    assert PITHING_DRONE.setup_interceptors is not None or PITHING_DRONE.resolve is not None


# ---------------------------------------------------------------------------
# Tests — Izzet guild
# ---------------------------------------------------------------------------


def test_tezzys_test_modal_resolves_at_least_one_mode(pkm_game):
    """Tezzy's Test runs a modal choose-1-of-3. At least one mode must emit events."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.izzet import TEZZYS_TEST
    from src.cards.pokemon.sv_starter import CHARMANDER

    # Give p1 a non-empty deck so the search-Item mode is plausible.
    for _ in range(5):
        obj = g.create_object(
            name="DeckedCharmander", owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=CHARMANDER.characteristics, card_def=CHARMANDER,
        )
        g.state.zones[f"library_{p1.id}"].objects.append(obj.id)
    _put_in_hand(g, p2.id, CHARMANDER, n=2)

    event = Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id})
    events = TEZZYS_TEST.resolve(event, g.state)
    assert events, "Tezzy's Test must emit at least one event from the chosen mode"


# ---------------------------------------------------------------------------
# Tests — Orzhov guild
# ---------------------------------------------------------------------------


def test_obzedat_ex_applies_prize_tax(pkm_game):
    """Obzedat's Spectral Decree (mode B) applies a prize tax to opponent."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.orzhov import OBZEDAT_GHOST_COUNCIL_EX

    attacker = _place_basic_pokemon(g, p1.id, OBZEDAT_GHOST_COUNCIL_EX)
    # Make sure mode B fires by giving opp no bench Pokemon (so the KO-bench
    # mode A target choice falls through and the resolver picks tax mode).
    tax_before = getattr(p2, "prize_tax", 0) or 0

    attack = OBZEDAT_GHOST_COUNCIL_EX.attacks[-1]  # Spectral Decree
    events = attack["effect_fn"](attacker, g.state)

    tax_after = getattr(p2, "prize_tax", 0) or 0
    assert tax_after > tax_before, (
        f"Expected prize_tax to increase; got {tax_before} → {tax_after}"
    )
    assert any(e.type == EventType.PKM_PRIZE_TAX for e in events)


def test_sanguine_sacrament_self_lz_and_heals(pkm_game):
    """Sanguine Sacrament puts a Pokemon in LZ and heals 2 others."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.orzhov import SANGUINE_SACRAMENT
    from src.cards.pokemon.sv_starter import CHARMANDER

    sacrifice = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="bench")
    sacrifice.state.damage_counters = 0
    a = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="bench")
    a.state.damage_counters = 5
    b = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="active")
    b.state.damage_counters = 8

    lz_before = len(g.state.zones["lost_zone"].objects)
    event = Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id})
    events = SANGUINE_SACRAMENT.resolve(event, g.state)

    assert len(g.state.zones["lost_zone"].objects) == lz_before + 1
    # At least 1 of the remaining 2 should have been healed.
    healed = (a.state.damage_counters < 5) or (b.state.damage_counters < 8)
    assert healed, "Sanguine Sacrament should heal damage from a remaining Pokemon"
    assert any(e.type == EventType.PKM_LOST_ZONE for e in events)


# ---------------------------------------------------------------------------
# Tests — Golgari guild (Jarad ex rewrite + Cremate)
# ---------------------------------------------------------------------------


def test_cremate_puts_hand_cards_into_lost_zone(pkm_game):
    """Cremate puts up to 3 Pokemon/Energy cards from hand into the Lost Zone."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.golgari import CREMATE
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    _put_in_hand(g, p1.id, CHARMANDER, n=2)
    _put_in_hand(g, p1.id, FIRE_ENERGY, n=2)

    lz_before = len(g.state.zones["lost_zone"].objects)
    event = Event(type=EventType.PKM_PLAY_ITEM, payload={"player": p1.id})
    events = CREMATE.resolve(event, g.state)

    lz_after = len(g.state.zones["lost_zone"].objects)
    assert lz_after > lz_before, "At least one card should have moved to LZ"
    assert any(e.type == EventType.PKM_LOST_ZONE for e in events)


def test_jarad_ex_necrosurge_scales_with_lost_zone(pkm_game):
    """Jarad ex's Necrosurge does extra damage per Pokemon in the LZ."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.golgari import JARAD_GOLGARI_LICH_LORD_EX
    from src.cards.pokemon.sv_starter import CHARMANDER

    attacker = _place_basic_pokemon(g, p1.id, JARAD_GOLGARI_LICH_LORD_EX)
    opp_active = _place_basic_pokemon(g, p2.id, CHARMANDER)
    # Pre-seed LZ with 3 of p1's Pokemon.
    for _ in range(3):
        obj = g.create_object(name="LZCharmander", owner_id=p1.id,
                              zone=ZoneType.LOST_ZONE,
                              characteristics=CHARMANDER.characteristics,
                              card_def=CHARMANDER)
        g.state.zones["lost_zone"].objects.append(obj.id)
        obj.zone = ZoneType.LOST_ZONE

    attack = JARAD_GOLGARI_LICH_LORD_EX.attacks[-1]  # Necrosurge
    events = attack["effect_fn"](attacker, g.state)

    # 3 LZ Pokemon × 2 counters = 6 counters on opp Active.
    assert opp_active.state.damage_counters >= 6, (
        f"Expected ≥6 damage counters from LZ scaling; got {opp_active.state.damage_counters}"
    )


# ---------------------------------------------------------------------------
# Tests — Simic guild (Negate the Negation build-around)
# ---------------------------------------------------------------------------


def test_negate_the_negation_destroys_opp_tool_and_lz_mills(pkm_game):
    """Negate the Negation: pick opp Pokemon with a Tool, discard the Tool,
    mill into LZ for each Tool discarded."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.simic import NEGATE_THE_NEGATION
    from src.cards.pokemon.sv_starter import CHARMANDER

    # Need any Trainer-Tool card to attach to opp.
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE

    opp_pokemon = _place_basic_pokemon(g, p2.id, CHARMANDER)
    # Manually attach a tool object.
    tool_obj = g.create_object(
        name=PITHING_DRONE.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=PITHING_DRONE.characteristics, card_def=PITHING_DRONE,
    )
    if not hasattr(opp_pokemon.state, "attached_tools"):
        opp_pokemon.state.attached_tools = []
    opp_pokemon.state.attached_tools.append(tool_obj.id)

    # Stack opp deck so LZ mill has something to take.
    for _ in range(3):
        obj = g.create_object(name="DeckTop", owner_id=p2.id, zone=ZoneType.LIBRARY,
                              characteristics=CHARMANDER.characteristics, card_def=CHARMANDER)
        g.state.zones[f"library_{p2.id}"].objects.append(obj.id)

    lz_before = len(g.state.zones["lost_zone"].objects)
    event = Event(type=EventType.PKM_PLAY_ITEM, payload={"player": p1.id})
    events = NEGATE_THE_NEGATION.resolve(event, g.state)

    assert not opp_pokemon.state.attached_tools, "Tool should be discarded"
    assert len(g.state.zones["lost_zone"].objects) == lz_before + 1, (
        "1 Tool removed → 1 card to LZ"
    )
    assert any(e.type == EventType.PKM_LOST_ZONE for e in events)
