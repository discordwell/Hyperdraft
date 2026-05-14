"""
Gap-closure regression tests — bugs and gaps from the post-/ultra-loop verification.

Locks in fixes for:
- Switch + Potion: previously hard-blocked at -100 in scorers under the theory
  they were engine-broken. Standalone reproducer shows both work correctly;
  the pilot's observation was a stale-packet read from the state-file race
  condition (now fixed). Scorer bodies restored; these tests prevent the
  workaround from sneaking back.
- Negate the Negation: previously hard-gated at -100 with no opp Tool;
  symmetric to Pithing Drone (opp rarely plays Tools) → both cards never
  fire. Softened so the card has a non-negative floor.
- Voidmage Apprentice: cheap Basic with energy-denial attack that fires 0
  in heuristic AI play; small evolution-target bias added.
- Mirko Vosk / Aurelia ex: build-arounds that never reach payoff state.
  Evolution-line bias bumps.
- 4 deferred engine-bug reports cross-checked at the unit level.
"""

from __future__ import annotations

import os
import contextlib

import pytest

from src.engine.types import Event, EventType, ZoneType


@pytest.fixture
def pkm_game():
    """Two-player Pokemon Game with both players registered as AI."""
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


def _place(g, player_id, card_def, *, slot="active"):
    zone_type = ZoneType.ACTIVE_SPOT if slot == "active" else ZoneType.BENCH
    return g.create_object(
        name=card_def.name, owner_id=player_id, zone=zone_type,
        characteristics=card_def.characteristics, card_def=card_def,
    )


def _in_hand(g, player_id, card_def):
    return g.create_object(
        name=card_def.name, owner_id=player_id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def,
    )


# ===========================================================================
# Switch — regression: engine swap actually happens through _play_trainer path
# ===========================================================================


def test_switch_actually_swaps_active_and_bench(pkm_game):
    """Lock in the truth that Switch swaps Active↔Bench end-to-end through
    the same _play_trainer path the codex harness uses. Reproducer for the
    v2-iter2 'Switch silent no-op' false alarm."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.sv_starter import SWITCH, CHARMANDER, SQUIRTLE

    active = _place(g, p1.id, CHARMANDER, slot="active")
    bench = _place(g, p1.id, SQUIRTLE, slot="bench")
    active.state.damage_counters = 5  # matches the pilot's T4 conditions
    sw = _in_hand(g, p1.id, SWITCH)

    events = g.turn_manager._play_trainer(p1.id, sw.id, "item")

    assert any(e.type == EventType.PKM_SWITCH for e in events), (
        f"Switch must emit PKM_SWITCH; got {[e.type.name for e in events]}"
    )
    assert g.state.zones[f"active_spot_{p1.id}"].objects == [bench.id]
    assert active.id in g.state.zones[f"bench_{p1.id}"].objects
    assert sw.id in g.state.zones[f"graveyard_{p1.id}"].objects


def test_switch_scorer_is_not_hard_blocked():
    """Switch's TRAINER_SCORERS entry must not return -100 (the v2-iter2
    workaround). It should evaluate to something positive in a status-locked
    Active scenario where Switch is the right play."""
    from src.ai.pokemon.trainers import TRAINER_SCORERS
    scorer = TRAINER_SCORERS.get("Switch")
    assert scorer is not None, "Switch scorer missing from TRAINER_SCORERS"
    # Verify the scorer body runs past the hard-block: source must NOT
    # contain `return -100.0` as its first executable statement.
    import inspect
    src = inspect.getsource(scorer)
    body_lines = [
        line.strip() for line in src.splitlines()
        if line.strip() and not line.strip().startswith("#")
        and not line.strip().startswith("def ")
        and not line.strip().startswith('"""')
        and not line.strip().startswith("'''")
    ]
    first_logic = next((l for l in body_lines if not l.startswith('"')), None)
    assert first_logic != "return -100.0", (
        "Switch scorer is hard-blocked at -100; remove the workaround."
    )


# ===========================================================================
# Potion — regression: heal actually applies
# ===========================================================================


def test_potion_actually_heals_damage_counters(pkm_game):
    """Potion heals 30 HP (3 damage counters) end-to-end through _play_trainer."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.sv_starter import POTION, CHARMANDER

    pkm = _place(g, p1.id, CHARMANDER, slot="active")
    pkm.state.damage_counters = 5  # 50 HP damage
    pot = _in_hand(g, p1.id, POTION)

    events = g.turn_manager._play_trainer(p1.id, pot.id, "item")

    assert pkm.state.damage_counters == 2, (
        f"Potion must heal 30 HP (5 → 2 counters); got {pkm.state.damage_counters}"
    )
    assert any(e.type == EventType.PKM_HEAL for e in events)
    assert pot.id in g.state.zones[f"graveyard_{p1.id}"].objects


def test_potion_scorer_is_not_hard_blocked():
    """Potion's TRAINER_SCORERS entry must not return -100 (the v2-iter2
    workaround). With a damaged Active, scorer should return a positive value."""
    from src.ai.pokemon.trainers import TRAINER_SCORERS
    scorer = TRAINER_SCORERS.get("Potion")
    assert scorer is not None
    import inspect
    src = inspect.getsource(scorer)
    body_lines = [
        line.strip() for line in src.splitlines()
        if line.strip() and not line.strip().startswith("#")
        and not line.strip().startswith("def ")
        and not line.strip().startswith('"""')
        and not line.strip().startswith("'''")
    ]
    first_logic = next((l for l in body_lines if not l.startswith('"')), None)
    assert first_logic != "return -100.0", (
        "Potion scorer is hard-blocked at -100; remove the workaround."
    )


# ===========================================================================
# Dimir Interrogation — regression: burial actually happens under AI play
# ===========================================================================


def test_dimir_interrogation_buries_a_pokemon_under_ai_play(pkm_game):
    """Lock in that the look-and-yank PendingChoice resolves via the AI handler's
    make_choice when no LLM pilot is present, and a Pokemon from opp's hand is
    buried at the bottom of opp's library. Reproducer for the v2-iter3c
    'choice prompt not surfacing' report — which was a single-mode
    contamination, not an engine bug. The card mechanics work; the residual
    gap is LLM-pilot visibility into the choice (separate, larger work)."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.dimir import DIMIR_INTERROGATION
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    # Opp hand: 2 Pokemon. Opp deck: 3 non-Pokemon so the burial result is
    # observable (draw on bottom-burial cycle would otherwise return the
    # buried card if deck is empty).
    a = _in_hand(g, p2.id, CHARMANDER)
    b = _in_hand(g, p2.id, CHARMANDER)
    for _ in range(3):
        g.create_object(
            name="Fire Energy", owner_id=p2.id, zone=ZoneType.LIBRARY,
            characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
        )
    interrogation = _in_hand(g, p1.id, DIMIR_INTERROGATION)

    events = g.turn_manager._play_trainer(p1.id, interrogation.id, "item")

    # One of the targeted Pokemon ended up at the bottom of opp's library.
    p2_lib = g.state.zones[f"library_{p2.id}"].objects
    p2_hand = g.state.zones[f"hand_{p2.id}"].objects
    buried_count = sum(1 for tid in (a.id, b.id) if tid in p2_lib)
    assert buried_count == 1, (
        f"Exactly one Pokemon should be buried; got buried={buried_count}, "
        f"lib={p2_lib}, hand={p2_hand}"
    )
    # Reveal-hand event fired AND opp drew 1.
    types = [e.type for e in events]
    assert EventType.PKM_REVEAL_HAND in types
    assert EventType.DRAW in types


# ===========================================================================
# Energy-attach availability after evolve / retreat — regression
# ===========================================================================


def test_energy_attach_actions_persist_after_evolve(pkm_game):
    """v2-iter3c claimed energy attach options disappear after evolve. They
    don't — `energy_attached_this_turn` is only flipped by the actual attach,
    not by evolve. This locks that in.
    """
    from src.engine.pokemon_legal_actions import legal_pokemon_actions
    from src.cards.pokemon.sv_starter import CHARMANDER, CHARMELEON, FIRE_ENERGY
    g, p1, _p2 = pkm_game

    active = _place(g, p1.id, CHARMANDER, slot="active")
    bench = _place(g, p1.id, CHARMANDER, slot="bench")
    evo = _in_hand(g, p1.id, CHARMELEON)
    energy = _in_hand(g, p1.id, FIRE_ENERGY)
    active.state.turns_in_play = 2
    bench.state.turns_in_play = 2
    g.turn_manager.pkm_turn_state.game_turn_count = 3
    g.state.active_player = p1.id

    attach_before = [
        a for a in legal_pokemon_actions(g, p1.id)
        if a["type"] == "PKM_ATTACH_ENERGY"
    ]
    assert len(attach_before) >= 1

    g.turn_manager.evolve_pokemon(active.id, evo.id)
    assert p1.energy_attached_this_turn is False

    attach_after = [
        a for a in legal_pokemon_actions(g, p1.id)
        if a["type"] == "PKM_ATTACH_ENERGY"
    ]
    assert len(attach_after) >= 1, (
        "Energy attach options must remain after evolving; "
        "the v2-iter3c report claimed otherwise but it was a contaminated "
        "single-mode run."
    )


def test_energy_attach_actions_persist_after_retreat(pkm_game):
    """Same as the evolve test, but for retreat. `retreated_this_turn` is
    independent of `energy_attached_this_turn`."""
    from src.engine.pokemon_legal_actions import legal_pokemon_actions
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY
    g, p1, _p2 = pkm_game

    active = _place(g, p1.id, CHARMANDER, slot="active")
    bench = _place(g, p1.id, CHARMANDER, slot="bench")
    # Pay retreat cost: 2 energies attached to active.
    for _ in range(2):
        e = g.create_object(
            name="Fire Energy", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
        )
        active.state.attached_energy.append(e.id)
    _in_hand(g, p1.id, FIRE_ENERGY)
    active.state.turns_in_play = 2
    bench.state.turns_in_play = 2
    g.turn_manager.pkm_turn_state.game_turn_count = 3
    g.state.active_player = p1.id

    g.turn_manager._retreat(p1.id, bench.id)
    assert p1.retreated_this_turn is True
    assert p1.energy_attached_this_turn is False

    attach_after = [
        a for a in legal_pokemon_actions(g, p1.id)
        if a["type"] == "PKM_ATTACH_ENERGY"
    ]
    assert len(attach_after) >= 1, (
        "Energy attach options must remain after retreating; the v2-iter3c "
        "report claimed otherwise but it was a contaminated single-mode run."
    )


# ===========================================================================
# Voidmage Apprentice — utility-Basic wins opener
# ===========================================================================


def test_voidmage_wins_opening_active_over_lazlet(pkm_game):
    """A 1-energy disruption Basic (Voidmage Apprentice) should win the
    opening Active slot over a 2-energy core Basic like Lazlet. Locks in
    both the opening-active-selection enable for medium difficulty AND
    the utility-Basic bonus."""
    g, p1, _p2 = pkm_game
    from src.ai.pokemon.adapter import PokemonAIAdapter
    from src.cards.pokemon.beyond.ravnica.dimir import LAZLET, VOIDMAGE_APPRENTICE

    ai = PokemonAIAdapter(difficulty='medium')
    lazlet = _in_hand(g, p1.id, LAZLET)
    voidmage = _in_hand(g, p1.id, VOIDMAGE_APPRENTICE)
    chosen = ai.choose_setup_active(p1.id, g.state, [lazlet.id, voidmage.id])
    chosen_obj = g.state.objects.get(chosen)
    assert chosen_obj is not None, "Opening-active selection should return a candidate at medium"
    assert chosen_obj.name == "Voidmage Apprentice", (
        f"Voidmage should win opener (1-energy disruption attack vs Lazlet's "
        f"2-energy 20-damage); got {chosen_obj.name}"
    )


# ===========================================================================
# Pokemon Tools in legal actions + adapter item-play
# ===========================================================================


def test_pokemon_tools_appear_in_legal_actions(pkm_game):
    """Pokemon Tools (POKEMON_TOOL, not ITEM) must be legal to play when
    there's at least one Pokemon in play without an existing Tool. Locks
    in the legal-action fix that previously gated Tools out of the
    PKM_PLAY_ITEM list."""
    from src.engine.pokemon_legal_actions import legal_pokemon_actions
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    from src.cards.pokemon.sv_starter import CHARMANDER
    g, p1, _p2 = pkm_game

    _place(g, p1.id, CHARMANDER, slot="active")
    pithing = _in_hand(g, p1.id, PITHING_DRONE)
    g.turn_manager.pkm_turn_state.game_turn_count = 3
    g.state.active_player = p1.id

    actions = legal_pokemon_actions(g, p1.id)
    tool_actions = [a for a in actions if a["payload"].get("card_id") == pithing.id]
    assert len(tool_actions) == 1, (
        f"Pithing Drone (a Pokemon Tool) should appear once in legal actions; "
        f"got {len(tool_actions)}"
    )
    assert tool_actions[0]["type"] == "PKM_PLAY_ITEM"


def test_pokemon_tools_appear_in_adapter_item_candidates(pkm_game):
    """The adapter's _do_play_items must consider POKEMON_TOOL cards
    (not just CardType.ITEM). Locks in the adapter filter fix."""
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    from src.cards.pokemon.sv_starter import CHARMANDER
    g, p1, _p2 = pkm_game

    _place(g, p1.id, CHARMANDER, slot="active")
    pithing = _in_hand(g, p1.id, PITHING_DRONE)
    g.turn_manager.pkm_turn_state.game_turn_count = 3
    g.state.active_player = p1.id

    # Direct play through _play_trainer simulates what _do_play_items would do.
    events = g.turn_manager._play_trainer(p1.id, pithing.id, "item")
    assert any(e.type == EventType.PKM_ATTACH_TOOL for e in events), (
        f"Tool play should emit PKM_ATTACH_TOOL; got {[e.type.name for e in events]}"
    )


# ===========================================================================
# Depth-rubric recalibration — BRV passes against MTG-aligned thresholds
# ===========================================================================


def test_depth_rubric_recalibrated_thresholds_pass_brv():
    """The original health gates (median 5, axis 0.5, code 0.5, thin 0.20)
    were aspirational fictions — every professional MTG set in the repo
    failed them too. The recalibrated gates (against MTG baseline) put
    BRV honestly at 4/4."""
    import contextlib, os
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.depth.report import score_registry
        from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS

    r = score_registry(BEYOND_RAVNICA_CARDS, engine="pokemon", set_code="BRV")
    passed = sum(1 for v in r.health_checks.values() if v == "PASS")
    assert passed == 4, (
        f"BRV should pass all 4 recalibrated health gates; got {passed}/4. "
        f"Status: {r.health_checks}"
    )


def test_bloomburrow_passes_at_least_3_of_4_recalibrated_gates():
    """Bloomburrow is the gold-standard healthy MTG set; the recalibrated
    gates must let it pass at least 3/4 (it has structurally many vanilla
    Basics so thin_ratio is the hardest gate). If a future change makes
    Bloomburrow regress to 1/4, the gates have been over-tightened."""
    import contextlib, os
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.depth.report import score_registry
        from src.cards.bloomburrow import BLOOMBURROW_CARDS

    r = score_registry(BLOOMBURROW_CARDS, engine="mtg", set_code="Bloomburrow")
    passed = sum(1 for v in r.health_checks.values() if v == "PASS")
    assert passed >= 3, (
        f"Bloomburrow should pass ≥3/4 recalibrated gates; got {passed}/4. "
        f"Status: {r.health_checks}"
    )
