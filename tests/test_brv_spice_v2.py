"""
Tests for the BRV spice pack v2 — engine-level fixes that close the
"scored well / plays mid" gap.

Phase 1 coverage:
  - prize_tax actually consumed by _take_prizes (Phase 1c)
  - Tool attachment slot binds via attach_tool (Phase 1b)
  - PendingChoice created and resolved for modal Trainer cards (Phase 1a)

Run:
    python -m pytest tests/test_brv_spice_v2.py -q
"""

from __future__ import annotations

import os
import contextlib

import pytest

from src.engine.types import (
    CardType, Event, EventType, ZoneType, PokemonType, Player,
)


# ---------------------------------------------------------------------------
# Fixture — minimal Pokemon game with all per-player zones
# ---------------------------------------------------------------------------


@pytest.fixture
def pkm_game():
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
    g = Game(mode="pokemon")
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    return g, p1, p2


def _place_basic_pokemon(g, player_id, card_def, slot="active"):
    zone_type = ZoneType.ACTIVE_SPOT if slot == "active" else ZoneType.BENCH
    return g.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=zone_type,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _seed_prize_zone(g, player_id, card_def, n=6):
    """Drop `n` placeholder prize cards into `player_id`'s prize_cards zone."""
    for _ in range(n):
        g.create_object(
            name="Prize",
            owner_id=player_id,
            zone=ZoneType.PRIZE_CARDS,
            characteristics=card_def.characteristics,
            card_def=card_def,
        )
    g.state.players[player_id].prizes_remaining = n


# ===========================================================================
# Phase 1c — prize_tax bug fix
# ===========================================================================


def test_prize_tax_absorbs_one_prize(pkm_game):
    """Setting player.prize_tax = 1 absorbs the next prize the player would
    take, leaving prize_tax = 0 and the prize zone untouched.

    This was a silent bug pre-Phase-1: pkm_apply_prize_tax wrote the marker
    but _take_prizes never read it, so Obzedat ex's mode B did nothing.
    """
    g, p1, p2 = pkm_game
    from src.cards.pokemon.sv_starter import CHARMANDER

    _seed_prize_zone(g, p1.id, CHARMANDER, n=6)
    p1.prize_tax = 1

    # Place a p2 Active and KO it directly via the combat manager.
    target = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="active")
    target.state.damage_counters = 99  # well over HP

    g.combat_manager.check_knockouts()

    assert p1.prizes_remaining == 6, (
        f"Tax should have absorbed the 1-prize KO; prizes={p1.prizes_remaining}"
    )
    assert p1.prize_tax == 0, "Tax should be decremented after absorption"


def test_prize_tax_two_partially_absorbs_ex_KO(pkm_game):
    """A 2-prize KO against a +1 tax: opponent takes 1 prize, tax → 0."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.sv_starter import CHARMANDER

    _seed_prize_zone(g, p1.id, CHARMANDER, n=6)
    p1.prize_tax = 1

    # Make the target a 2-prize Pokemon by mutating prize_count.
    target = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="active")
    # CardDefinition is frozen-ish; for the test we patch the obj's card_def
    # in-place. Real ex cards declare prize_count=2.
    import dataclasses
    target.card_def = dataclasses.replace(target.card_def, prize_count=2)
    target.state.damage_counters = 99

    g.combat_manager.check_knockouts()

    assert p1.prizes_remaining == 5, (
        f"Should have taken 1 of 2 prizes (tax absorbed 1); got {p1.prizes_remaining}"
    )
    assert p1.prize_tax == 0


def test_prize_tax_zero_is_noop(pkm_game):
    """With no tax set, prize-taking works exactly as before."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.sv_starter import CHARMANDER

    _seed_prize_zone(g, p1.id, CHARMANDER, n=6)
    assert p1.prize_tax == 0  # default

    target = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="active")
    target.state.damage_counters = 99

    g.combat_manager.check_knockouts()

    assert p1.prizes_remaining == 5  # one prize taken


# ===========================================================================
# Phase 1b — Tool attachment slot
# ===========================================================================


def test_attach_tool_sets_back_pointers(pkm_game):
    """attach_tool binds tool to holder via both back-pointers."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    from src.cards.pokemon.sv_starter import CHARMANDER
    from src.cards.pokemon._tool_helpers import attach_tool

    holder = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="active")
    tool = g.create_object(
        name=PITHING_DRONE.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=PITHING_DRONE.characteristics, card_def=PITHING_DRONE,
    )
    assert tool.state.attached_to is None
    assert holder.state.attached_tool is None

    events = attach_tool(tool.id, holder.id, g.state, source=tool.id)

    assert tool.state.attached_to == holder.id
    assert holder.state.attached_tool == tool.id
    assert any(e.type == EventType.PKM_ATTACH_TOOL for e in events)
    # Tool removed from hand zone container
    assert tool.id not in g.state.zones[f"hand_{p1.id}"].objects


def test_attach_tool_displaces_existing_tool(pkm_game):
    """Attaching a second tool to a holder discards the first and emits detach."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    from src.cards.pokemon.sv_starter import CHARMANDER
    from src.cards.pokemon._tool_helpers import attach_tool

    holder = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="active")
    tool_a = g.create_object(
        name="Tool A", owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=PITHING_DRONE.characteristics, card_def=PITHING_DRONE,
    )
    tool_b = g.create_object(
        name="Tool B", owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=PITHING_DRONE.characteristics, card_def=PITHING_DRONE,
    )

    attach_tool(tool_a.id, holder.id, g.state)
    events = attach_tool(tool_b.id, holder.id, g.state)

    assert holder.state.attached_tool == tool_b.id
    assert tool_a.state.attached_to is None
    assert tool_a.id in g.state.zones[f"graveyard_{p1.id}"].objects
    assert any(e.type == EventType.PKM_DETACH_TOOL for e in events)


def test_tool_detaches_on_holder_ko(pkm_game):
    """When the holder is KO'd, the attached Tool goes to discard with a
    PKM_DETACH_TOOL event. Pithing Drone's interceptor fires on the same
    KO and discards the attacker's energy."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY
    from src.cards.pokemon._tool_helpers import attach_tool

    _seed_prize_zone(g, p2.id, CHARMANDER, n=6)

    # p1's Active is the holder; p2's Active is the would-be KO'er.
    holder = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="active")
    attacker = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="active")

    # Attach Pithing Drone to the holder. setup_interceptors already ran
    # at create_object time.
    tool = g.create_object(
        name=PITHING_DRONE.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=PITHING_DRONE.characteristics, card_def=PITHING_DRONE,
    )
    attach_tool(tool.id, holder.id, g.state)

    # Energy on attacker so we have something to discard.
    for _ in range(3):
        e = g.create_object(
            name="Fire Energy", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
        )
        attacker.state.attached_energy.append(e.id)

    # Manually KO the holder via the combat manager. The KO event's payload
    # needs an attacker_id so Pithing Drone's filter passes.
    holder.state.damage_counters = 99
    # The combat manager emits PKM_KNOCKOUT internally — but its payload
    # doesn't always include attacker_id. We piggyback by setting
    # last_damage_source on the holder, then emit the KO event directly.
    holder.state.last_damage_source = attacker.id
    # Use handle_knockout (which emits PKM_KNOCKOUT with no attacker_id by
    # default — so we wrap and inject the attacker for the test).
    from src.engine.types import Event as _Event
    pre_attacker_energy = len(attacker.state.attached_energy)
    g.pipeline.emit(_Event(
        type=EventType.PKM_KNOCKOUT,
        payload={
            'pokemon_id': holder.id, 'owner': p1.id, 'attacker_id': attacker.id,
            'prize_count': 1, 'was_active': True,
        },
        source=holder.id,
    ))
    # Now run the combat manager's KO bookkeeping (detaches Tool, etc.).
    g.combat_manager.check_knockouts()

    assert holder.state.attached_tool is None
    assert tool.state.attached_to is None
    assert tool.id in g.state.zones[f"graveyard_{p1.id}"].objects
    # Pithing Drone's interceptor should have discarded the attacker's energy.
    assert len(attacker.state.attached_energy) < pre_attacker_energy, (
        f"Pithing Drone should have discarded attacker's energy; "
        f"before={pre_attacker_energy} after={len(attacker.state.attached_energy)}"
    )


def test_pithing_drone_does_not_fire_when_unattached(pkm_game):
    """When Pithing Drone hasn't been attached, its interceptor must NOT
    fire on KOs in the game — the filter gates on attached_to."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    # Create the tool but DON'T attach it.
    tool = g.create_object(
        name=PITHING_DRONE.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=PITHING_DRONE.characteristics, card_def=PITHING_DRONE,
    )
    assert tool.state.attached_to is None

    attacker = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="active")
    for _ in range(3):
        e = g.create_object(
            name="Fire Energy", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
        )
        attacker.state.attached_energy.append(e.id)
    pre_energy = len(attacker.state.attached_energy)

    # KO an unrelated p1 Pokemon (without the tool attached).
    victim = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="bench")
    g.pipeline.emit(Event(
        type=EventType.PKM_KNOCKOUT,
        payload={
            'pokemon_id': victim.id, 'owner': p1.id, 'attacker_id': attacker.id,
            'prize_count': 1, 'was_active': False,
        },
        source=victim.id,
    ))

    # Pithing Drone's filter should reject (attached_to is None).
    assert len(attacker.state.attached_energy) == pre_energy, (
        "Unattached Pithing Drone must NOT discard energy"
    )


def test_play_trainer_attaches_pokemon_tool(pkm_game):
    """Playing a POKEMON_TOOL Trainer via _play_trainer attaches to a
    chosen own Pokemon and does NOT send the Tool to graveyard."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.beyond.ravnica.azorius import PITHING_DRONE
    from src.cards.pokemon.sv_starter import CHARMANDER

    holder = _place_basic_pokemon(g, p1.id, CHARMANDER, slot="active")

    # Put the tool in p1's hand.
    tool = g.create_object(
        name=PITHING_DRONE.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=PITHING_DRONE.characteristics, card_def=PITHING_DRONE,
    )

    events = g.turn_manager._play_trainer(p1.id, tool.id, 'item')

    assert any(e.type == EventType.PKM_ATTACH_TOOL for e in events)
    assert holder.state.attached_tool == tool.id
    assert tool.state.attached_to == holder.id
    assert tool.id not in g.state.zones[f"graveyard_{p1.id}"].objects


# ===========================================================================
# Phase 1a — PendingChoice for Pokemon modal Trainers
# ===========================================================================


def test_pkm_modal_choice_creates_and_resolves_pending_choice(pkm_game):
    """pkm_modal_choice creates a real PendingChoice (visible while
    unresolved) and synchronously resolves it for AI players via the
    dispatcher's callback_data['handler'] path."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon._helpers import pkm_modal_choice

    # Set up: the resolving player is "AI" (so make_choice fires).
    from src.ai.pokemon.adapter import PokemonAIAdapter
    ai = PokemonAIAdapter()
    g.turn_manager.set_ai_handler(ai)
    g.turn_manager.set_ai_player(p1.id)

    # Two modes with side-effect-only callables for testability.
    log_a, log_b = [], []
    def mode_a(_state):
        log_a.append("ran")
        return [Event(type=EventType.PKM_HEAL, payload={"mode": "A"}, source="test")]
    def mode_b(_state):
        log_b.append("ran")
        return [Event(type=EventType.PKM_HEAL, payload={"mode": "B"}, source="test")]

    events = pkm_modal_choice(
        p1.id, g.state,
        source="TestCard",
        mode_names=("Heal A", "Heal B"),
        mode_effects=(mode_a, mode_b),
        heuristic_pick=1,  # request mode B
    )

    # Choice was created, resolved, and cleared in the same call.
    assert g.state.pending_choice is None
    # Heuristic pick honored: mode B ran, not mode A.
    assert log_b == ["ran"], "Mode B (heuristic pick) should have run"
    assert log_a == [], "Mode A should NOT have run"
    # Events flowed through dispatcher: PKM_USE_ABILITY log + mode-B heal.
    types = [e.type for e in events]
    assert EventType.PKM_USE_ABILITY in types
    heal_events = [e for e in events if e.type == EventType.PKM_HEAL]
    assert any(e.payload.get("mode") == "B" for e in heal_events)


def test_pkm_modal_choice_no_ai_leaves_choice_pending_for_human(pkm_game):
    """When the choosing player is NOT registered as AI, the shared
    ``resolve_pending_choice_inline`` (engine/pending_choice_helpers.py)
    correctly LEAVES the choice on state.pending_choice for the session
    layer to surface to a human — it does NOT silently auto-resolve.

    This locks down the post-iter-1 refactor that moved the helper out
    of ``_helpers.py`` and into the engine. Old behavior was a silent
    [0] auto-pick on the human path; now humans block on the choice via
    the API as intended.
    """
    g, p1, _p2 = pkm_game
    from src.cards.pokemon._helpers import pkm_modal_choice

    # Disable AI for this test: pop p1 out of ai_players so the helper
    # treats this as a human choice.
    g.turn_manager.ai_players.discard(p1.id)

    log = []
    def mode_a(_s):
        log.append("A")
        return []
    def mode_b(_s):
        log.append("B")
        return []

    events = pkm_modal_choice(
        p1.id, g.state, source="t",
        mode_names=("A", "B"),
        mode_effects=(mode_a, mode_b),
        heuristic_pick=1,
    )

    # Neither mode ran; choice is pending for the human.
    assert log == [], f"No mode should run on the human path; got {log}"
    assert events == [], f"No events on the human path; got {events}"
    assert g.state.pending_choice is not None, (
        "Choice should remain pending for the session layer to surface"
    )
    assert g.state.pending_choice.choice_type == "pkm_modal_with_callback"


def test_pkm_modal_choice_ai_make_choice_overrides_heuristic(pkm_game):
    """The AI handler's make_choice value wins over the helper's
    heuristic_pick. This is the PendingChoice surface the ultra-loop /
    LLM pilot will use later to override card behavior."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon._helpers import pkm_modal_choice
    from src.ai.pokemon.adapter import PokemonAIAdapter

    class OverridingAI(PokemonAIAdapter):
        def make_choice(self, player_id, choice, state):
            return [0]  # Always pick mode 0, ignoring heuristic_pick

    g.turn_manager.set_ai_handler(OverridingAI())
    g.turn_manager.set_ai_player(p1.id)

    log = []
    def mode_a(_s):
        log.append("A")
        return []
    def mode_b(_s):
        log.append("B")
        return []

    pkm_modal_choice(
        p1.id, g.state, source="t",
        mode_names=("A", "B"),
        mode_effects=(mode_a, mode_b),
        heuristic_pick=1,  # helper would prefer B, but AI says A
    )

    assert log == ["A"], "AI's make_choice should override heuristic_pick"


def test_pkm_force_opp_choose_bench_routes_through_pending_choice(pkm_game):
    """pkm_force_opp_choose_bench creates a PendingChoice whose .player is
    opp_id, so the OPP's AI picks (against opp's interest per real rules)."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon._helpers import pkm_force_opp_choose_bench
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY
    from src.ai.pokemon.adapter import PokemonAIAdapter

    # Opp has 2 bench Pokemon — give one extra investment.
    bench_low = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="bench")
    bench_high = _place_basic_pokemon(g, p2.id, CHARMANDER, slot="bench")
    for _ in range(3):
        e = g.create_object(name="E", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
                            characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY)
        bench_high.state.attached_energy.append(e.id)

    # Opp is AI. Capture which player_id make_choice was called for.
    seen_chooser = []
    class CaptureAI(PokemonAIAdapter):
        def make_choice(self, player_id, choice, state):
            seen_chooser.append(player_id)
            # Honor heuristic_pick.
            return [choice.callback_data.get('heuristic_pick')]
    g.turn_manager.set_ai_handler(CaptureAI())
    g.turn_manager.set_ai_player(p2.id)

    chosen = pkm_force_opp_choose_bench(p2.id, g.state, source="test")

    # The chooser must be opp (p2), not the source's controller.
    assert seen_chooser == [p2.id], f"Expected p2 to choose, got {seen_chooser}"
    # Heuristic = bench_high (most invested).
    assert chosen == bench_high.id


def test_pkm_choose_from_hand_n_creates_multi_pick_choice(pkm_game):
    """pkm_choose_from_hand_n creates a multi-select PendingChoice
    (max_choices=n), and the AI's make_choice can return multiple IDs."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon._helpers import pkm_choose_from_hand_n
    from src.cards.pokemon.sv_starter import CHARMANDER
    from src.ai.pokemon.adapter import PokemonAIAdapter

    cards = _put_in_hand(g, p1.id, CHARMANDER, n=5) if False else []
    # Inline put_in_hand to avoid v1 fixture dependency.
    for _ in range(5):
        c = g.create_object(name="C", owner_id=p1.id, zone=ZoneType.HAND,
                            characteristics=CHARMANDER.characteristics, card_def=CHARMANDER)
        cards.append(c)
    seen_max = []
    class CaptureAI(PokemonAIAdapter):
        def make_choice(self, player_id, choice, state):
            seen_max.append(choice.max_choices)
            # Pick first 2.
            return [c.id for c in cards[:2]]
    g.turn_manager.set_ai_handler(CaptureAI())
    g.turn_manager.set_ai_player(p1.id)

    picked = pkm_choose_from_hand_n(g.state, controller=p1.id, n=3)

    assert seen_max == [3], "PendingChoice.max_choices should match n"
    assert len(picked) == 2 and all(isinstance(p, str) for p in picked)


def _put_in_hand(g, player_id, card_def, n=1):
    """Local helper for v2 tests (mirrors v1 fixture)."""
    out = []
    for _ in range(n):
        out.append(g.create_object(
            name=card_def.name, owner_id=player_id, zone=ZoneType.HAND,
            characteristics=card_def.characteristics, card_def=card_def,
        ))
    return out


# ===========================================================================
# Phase 3a — POKEMON_BIAS_PRESETS
# ===========================================================================


def test_pokemon_bias_presets_symbol_exists():
    """ultra-loop greps for POKEMON_BIAS_PRESETS — name must be exact."""
    from src.ai.pokemon.biases import POKEMON_BIAS_PRESETS
    assert isinstance(POKEMON_BIAS_PRESETS, dict)
    expected = {'balanced', 'aggro_burn', 'control_disrupt',
                'lz_engine', 'bench_swarm', 'energy_denial'}
    assert expected.issubset(set(POKEMON_BIAS_PRESETS.keys())), (
        f"Missing presets: {expected - set(POKEMON_BIAS_PRESETS.keys())}"
    )


def test_adapter_bias_kwarg_is_orthogonal_to_difficulty():
    """bias= is a new kwarg; 20+ existing call sites that pass only
    difficulty= must still work unchanged."""
    from src.ai.pokemon.adapter import PokemonAIAdapter
    # Old-style call: just difficulty.
    a1 = PokemonAIAdapter(difficulty="medium")
    assert a1.bias == "balanced"
    # New-style: both.
    a2 = PokemonAIAdapter(difficulty="hard", bias="lz_engine")
    assert a2.difficulty == "hard"
    assert a2.bias == "lz_engine"


def test_bias_attack_multipliers_change_scores():
    """A card with a bias multiplier of 2.0 should score ~2x compared to
    'balanced' (which leaves it at 1.0×)."""
    from src.ai.pokemon.adapter import PokemonAIAdapter
    from src.ai.pokemon.biases import apply_attack_bias, get_preset

    balanced = get_preset('balanced')
    lz = get_preset('lz_engine')
    base_score = 50.0

    base_balanced = apply_attack_bias(
        balanced, 'Mirko Vosk, Mind Drinker', 'Lost Recall', base_score)
    base_lz = apply_attack_bias(
        lz, 'Mirko Vosk, Mind Drinker', 'Lost Recall', base_score)

    assert base_balanced == 50.0  # multiplier 1.0
    assert base_lz == 100.0  # multiplier 2.0


def test_set_player_bias_overrides_per_player():
    """In a Dimir LZ vs Boros bench matchup, each player needs a
    different bias preset."""
    from src.ai.pokemon.adapter import PokemonAIAdapter

    a = PokemonAIAdapter(difficulty="medium", bias="balanced")
    a.set_player_bias("p1", "lz_engine")
    a.set_player_bias("p2", "bench_swarm")

    assert a._get_bias("p1") == "lz_engine"
    assert a._get_bias("p2") == "bench_swarm"
    # Player not set falls back to global bias.
    assert a._get_bias("p3") == "balanced"


# ===========================================================================
# Item 1 — Evolver starvation fix (Lazlet/Aurelet 4→6)
# ===========================================================================


def test_dimir_deck_lazlet_starvation_fix():
    """Lazlet is the engine starter. Iter-2 ultra-loop pilot drew 0
    Lazlet across 22 turns from 4 copies. Bumped to 6; lock that in."""
    from src.cards.pokemon.beyond.ravnica.dimir import make_dimir_deck
    from collections import Counter
    deck = make_dimir_deck()
    counts = Counter(c.name for c in deck)
    assert len(deck) == 60, f"Dimir deck should be 60 cards; got {len(deck)}"
    assert counts.get("Lazlet", 0) >= 6, (
        f"Lazlet must be ≥6 copies (was 4 pre-fix); got {counts.get('Lazlet', 0)}"
    )
    assert counts.get("Mirklet", 0) >= 4, (
        f"Mirklet must be ≥4 copies (was 3 pre-fix); got {counts.get('Mirklet', 0)}"
    )


def test_boros_deck_aurelet_starvation_fix():
    """Aurelet is the bench-swarm engine starter. Pilot drew 0 across
    iter 1+2+3 from 4 copies. Bumped to 6; lock that in."""
    from src.cards.pokemon.beyond.ravnica.boros import make_boros_deck
    from collections import Counter
    deck = make_boros_deck()
    counts = Counter(c.name for c in deck)
    assert len(deck) == 60, f"Boros deck should be 60 cards; got {len(deck)}"
    assert counts.get("Aurelet", 0) >= 6, (
        f"Aurelet must be ≥6 copies (was 4 pre-fix); got {counts.get('Aurelet', 0)}"
    )


# ===========================================================================
# Engine triage fixes — surface silent whiffs as PKM_REVEAL markers
# ===========================================================================


def _bump_turn_count(g, n=3):
    """Push past the Rare Candy / first-turn engine guards (>2)."""
    if g.turn_manager and getattr(g.turn_manager, "pkm_turn_state", None):
        g.turn_manager.pkm_turn_state.game_turn_count = n


def test_rare_candy_no_stage2_in_hand_emits_whiff_marker(pkm_game):
    """Bug 1: Rare Candy with a Basic on the bench but no Stage 2 in hand
    used to silently return []. Now it emits a PKM_REVEAL marker so the
    pilot sees the whiff (the card is still consumed by _play_trainer)."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.sv_starter import CHARMANDER, _rare_candy_effect
    _bump_turn_count(g)

    # Basic on bench, hand has no Stage 2.
    _place_basic_pokemon(g, p1.id, CHARMANDER, slot="bench")
    bench_basic = g.state.zones[f"bench_{p1.id}"].objects[0]
    g.state.objects[bench_basic].state.turns_in_play = 1
    # Hand intentionally empty of Stage 2 cards.
    ev = Event(type=EventType.PKM_PLAY_ITEM, payload={"player": p1.id})

    out = _rare_candy_effect(ev, g.state)

    assert any(
        e.type == EventType.PKM_REVEAL
        and e.payload.get("result") == "rare_candy_no_target"
        and e.payload.get("player") == p1.id
        for e in out
    ), f"Expected rare_candy_no_target marker; got {[(e.type, e.payload) for e in out]}"


def test_energy_attach_label_disambiguates_same_name_active_and_bench(pkm_game):
    """Bug 2: with two Pokemon of the same name (one Active, one Bench),
    the energy-attach labels used to be identical. Now they're suffixed
    with (Active) / (Bench)."""
    g, p1, _p2 = pkm_game
    from src.engine.pokemon_legal_actions import legal_pokemon_actions
    from src.cards.pokemon.sv_starter import CHARMANDER, FIRE_ENERGY

    _place_basic_pokemon(g, p1.id, CHARMANDER, slot="active")
    _place_basic_pokemon(g, p1.id, CHARMANDER, slot="bench")
    # Energy in hand to trigger the attach actions.
    g.create_object(
        name=FIRE_ENERGY.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
    )

    actions = legal_pokemon_actions(g, p1.id)
    attach_labels = [
        a["label"] for a in actions if a["type"] == "PKM_ATTACH_ENERGY"
    ]
    # Both targets present, distinguishable.
    assert any("(Active)" in label for label in attach_labels), (
        f"Expected (Active) suffix; got {attach_labels}"
    )
    assert any("(Bench)" in label for label in attach_labels), (
        f"Expected (Bench) suffix; got {attach_labels}"
    )
    # Sanity: no two labels are identical.
    assert len(set(attach_labels)) == len(attach_labels), (
        f"Attach labels should be unique; got duplicates in {attach_labels}"
    )


def test_professors_research_partial_draw_emits_marker(pkm_game):
    """Bug 3: when library has < 7 cards, Pro Research draws what's there
    but used to emit only the DRAW event. Now it ALSO emits a PKM_REVEAL
    marker so pilots can distinguish 'card bug' from 'deck-out edge'."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.sv_starter import CHARMANDER, _professors_research_effect

    # Seed library with only 3 cards (well under 7).
    for _ in range(3):
        g.create_object(
            name=CHARMANDER.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=CHARMANDER.characteristics, card_def=CHARMANDER,
        )
    ev = Event(type=EventType.PKM_PLAY_SUPPORTER, payload={"player": p1.id})

    out = _professors_research_effect(ev, g.state)

    # Original DRAW event still emitted.
    assert any(e.type == EventType.DRAW for e in out), (
        f"DRAW event should still be emitted; got {[(e.type, e.payload) for e in out]}"
    )
    # New marker present with the right payload.
    markers = [
        e for e in out
        if e.type == EventType.PKM_REVEAL
        and e.payload.get("result") == "professors_research_partial_draw"
    ]
    assert markers, f"Expected partial_draw marker; got {[(e.type, e.payload) for e in out]}"
    assert markers[0].payload.get("requested") == 7
    assert markers[0].payload.get("available") == 3
    assert markers[0].payload.get("player") == p1.id


def test_ultra_ball_no_basic_in_deck_emits_marker(pkm_game):
    """Bug 4: Ultra Ball pays the 2-card discard cost, then if no Basic
    Pokemon exists in the deck used to silently return []. Now emits a
    PKM_REVEAL marker so pilot sees the whiff."""
    g, p1, _p2 = pkm_game
    from src.cards.pokemon.sv_starter import (
        CHARMANDER, FIRE_ENERGY, _ultra_ball_effect,
    )

    # Hand needs >=2 cards (the discard cost).
    for _ in range(2):
        g.create_object(
            name=FIRE_ENERGY.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
        )
    # Library has only Energy — no Basic Pokemon to find.
    for _ in range(5):
        g.create_object(
            name=FIRE_ENERGY.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=FIRE_ENERGY.characteristics, card_def=FIRE_ENERGY,
        )
    # Bench non-empty so the "need_basic_for_bench" hard filter doesn't kick in
    # (the bug we're locking in is about no-Basic-in-deck, not the bench guard).
    _place_basic_pokemon(g, p1.id, CHARMANDER, slot="bench")

    ev = Event(type=EventType.PKM_PLAY_ITEM, payload={"player": p1.id})

    out = _ultra_ball_effect(ev, g.state)

    assert any(
        e.type == EventType.PKM_REVEAL
        and e.payload.get("result") == "ultra_ball_no_basic_in_deck"
        and e.payload.get("player") == p1.id
        for e in out
    ), f"Expected ultra_ball_no_basic_in_deck marker; got {[(e.type, e.payload) for e in out]}"


# ===========================================================================
# Item 4 — Cross-turn opp deck observation
# ===========================================================================


def test_turn_context_carries_opp_observed_types(pkm_game):
    """The TurnContext now exposes opp_observed_types (set of pokemon
    types seen across the game) and turn_number. The adapter populates
    both from its persistent _opp_observation_state."""
    g, p1, p2 = pkm_game
    from src.cards.pokemon.sv_starter import CHARMANDER, SQUIRTLE  # Fire R + Water W
    from src.ai.pokemon.adapter import PokemonAIAdapter

    # p2 is "opp" from p1's perspective. Place a Fire Pokemon (Charmander).
    _place_basic_pokemon(g, p2.id, CHARMANDER, slot="active")

    ai = PokemonAIAdapter()
    ctx = ai._build_turn_context(p1.id, g.state)

    assert hasattr(ctx, 'opp_observed_types')
    assert hasattr(ctx, 'turn_number')
    assert "R" in ctx.opp_observed_types, (
        f"Should have observed Fire (R) on opp; saw {ctx.opp_observed_types}"
    )

    # Now opp evolves / changes — observation set should accumulate.
    _place_basic_pokemon(g, p2.id, SQUIRTLE, slot="bench")
    ctx2 = ai._build_turn_context(p1.id, g.state)
    assert "R" in ctx2.opp_observed_types  # still remembers Fire
    assert "W" in ctx2.opp_observed_types  # newly added Water


def test_lazav_ex_wall_evolution_bonus_when_opp_lacks_darkness(pkm_game):
    """The Lazav ex evolution scorer applies a +25 bonus when opp has
    shown no Darkness attacker by turn 5+ (the 280 HP wall becomes
    effectively unkillable vs Boros's 80 max DPS)."""
    g, _p1, _p2 = pkm_game
    from src.ai.pokemon.adapter import PokemonAIAdapter
    from src.ai.pokemon.brv_spice_attack_scorers import _bias_evolve_lazav

    ai = PokemonAIAdapter()
    ai._current_context = type('Ctx', (), {})()
    # Opp shown no Darkness yet, turn 5+ — bonus should fire.
    ai._current_context.turn_number = 6
    ai._current_context.opp_observed_types = {"R", "F"}  # Fire + Fighting (Boros)
    bonus = _bias_evolve_lazav(ai, None, None, g.state, "p1")
    assert bonus >= 25.0, f"Wall bonus should fire (opp has no D); got {bonus}"

    # Opp HAS shown Darkness — bonus should NOT fire.
    ai._current_context.opp_observed_types = {"R", "F", "D"}
    bonus2 = _bias_evolve_lazav(ai, None, None, g.state, "p1")
    assert bonus2 < 15.0, f"Wall bonus should NOT fire (opp has D); got {bonus2}"

    # Early game — bonus should NOT fire (haven't had time to observe).
    ai._current_context.turn_number = 2
    ai._current_context.opp_observed_types = set()  # nothing seen yet
    bonus3 = _bias_evolve_lazav(ai, None, None, g.state, "p1")
    assert bonus3 < 15.0, f"Wall bonus should NOT fire pre-turn-5; got {bonus3}"
