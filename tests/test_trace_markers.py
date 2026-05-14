"""
Regression tests for the auto-derived ``CardDefinition.fire_markers``
field and the BRV event-trace's marker-discovery refactor.

Previously the event-trace shipped a hand-maintained
``SPICE_FIRE_MARKERS`` dict that silently drifted as new cards landed.
Now markers are derived at card-construction time
(name + Pokemon attack names) and read back off ``card_def.fire_markers``
at trace-run time. These tests lock that in.

Run:
    python -m pytest tests/test_trace_markers.py -q
"""

from __future__ import annotations

import contextlib
import os

import pytest


# ---------------------------------------------------------------------------
# 1) Auto-population at card-construction time
# ---------------------------------------------------------------------------


def test_pokemon_fire_markers_include_name_and_attack_names():
    """Pokemon cards: markers = {name} ∪ {attack["name"] for attack in attacks}.

    Voidmage Apprentice was the canary for this — its effect_fn passes
    ``source=attacker.id`` so the trace can only detect it by attack name
    ("Energy Drain"). The auto-derivation must include attack names.
    """
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon.beyond.ravnica.dimir import VOIDMAGE_APPRENTICE

    assert "Voidmage Apprentice" in VOIDMAGE_APPRENTICE.fire_markers
    assert "Energy Drain" in VOIDMAGE_APPRENTICE.fire_markers
    assert isinstance(VOIDMAGE_APPRENTICE.fire_markers, frozenset), (
        "fire_markers must be frozen (dataclasses can't have mutable defaults)"
    )


def test_pokemon_with_multiple_attacks_captures_all_attack_names():
    """Multi-attack Pokemon must include every attack name as a marker.

    Obzedat ex has both "Soul's Tax" and "Spectral Decree"; both must end
    up in the marker set.
    """
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon.beyond.ravnica.orzhov import OBZEDAT_GHOST_COUNCIL_EX

    markers = OBZEDAT_GHOST_COUNCIL_EX.fire_markers
    assert "Obzedat, Ghost Council ex" in markers
    assert "Soul's Tax" in markers
    assert "Spectral Decree" in markers


def test_trainer_card_markers_are_just_the_card_name():
    """Trainer cards (Item/Supporter/Stadium/Tool) have no attacks; their
    default markers are just the card name. The card's effect_fn emits
    events with ``source=<card name>`` (e.g. "Dimir Interrogation") so a
    single-name marker is sufficient."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon.beyond.ravnica.dimir import DIMIR_INTERROGATION

    assert DIMIR_INTERROGATION.fire_markers == frozenset({"Dimir Interrogation"})


def test_mtg_creature_default_markers_include_name():
    """make_creature (and other non-Pokemon constructors) default to
    ``{name}`` since there are no attack-name aliases to surface."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import make_creature

    card = make_creature(name="Test Creature", power=1, toughness=1)
    assert card.fire_markers == frozenset({"Test Creature"})


# ---------------------------------------------------------------------------
# 2) Explicit override is non-destructive
# ---------------------------------------------------------------------------


def test_explicit_fire_markers_override_default_set():
    """Card factories accept an explicit ``fire_markers`` arg. When
    provided, it replaces the default rather than getting silently
    overwritten by name+attacks."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import make_creature

    custom = frozenset({"Custom Tag", "Other Tag"})
    card = make_creature(
        name="X", power=1, toughness=1, fire_markers=custom,
    )
    assert card.fire_markers == custom
    assert "X" not in card.fire_markers, (
        "Explicit fire_markers must NOT be merged with the default name "
        "set — the caller is asserting they know the full marker list."
    )


def test_explicit_fire_markers_works_for_pokemon():
    """Same override semantics apply to ``make_pokemon`` — explicit
    markers replace the default name+attack-names set."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import make_pokemon

    card = make_pokemon(
        name="X",
        hp=10,
        pokemon_type="C",
        attacks=[{"name": "Foo", "cost": [], "damage": 0}],
        fire_markers={"OnlyThis"},
    )
    assert card.fire_markers == frozenset({"OnlyThis"})


# ---------------------------------------------------------------------------
# 3) Trace detects a known-firing card in a sample run
# ---------------------------------------------------------------------------


def test_trace_detects_voidmage_attack_in_minimal_game():
    """The Voidmage Apprentice attack ("Energy Drain") emits events sourced
    by attacker instance ID — the trace can only detect it via the
    auto-derived attack-name marker. Verify end-to-end through the same
    matching logic the BRV trace uses."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.engine.types import ZoneType
        from src.cards.pokemon.beyond.ravnica.dimir import VOIDMAGE_APPRENTICE
        from src.cards.pokemon.sv_starter import CHARMANDER, PSYCHIC_ENERGY
        from scripts.play.brv_spice_event_trace import _did_card_fire

    g = Game(mode="pokemon")
    p1 = g.add_player("attacker")
    p2 = g.add_player("defender")
    a = g.create_object(
        name=VOIDMAGE_APPRENTICE.name, owner_id=p1.id, zone=ZoneType.ACTIVE_SPOT,
        characteristics=VOIDMAGE_APPRENTICE.characteristics,
        card_def=VOIDMAGE_APPRENTICE,
    )
    b = g.create_object(
        name=CHARMANDER.name, owner_id=p2.id, zone=ZoneType.ACTIVE_SPOT,
        characteristics=CHARMANDER.characteristics, card_def=CHARMANDER,
    )
    e = g.create_object(
        name="Psychic Energy", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=PSYCHIC_ENERGY.characteristics, card_def=PSYCHIC_ENERGY,
    )
    a.state.attached_energy.append(e.id)
    g.state.active_player = p1.id

    captured = []
    original_emit = g.pipeline.emit

    def trace_emit(event):
        try:
            captured.append({
                "type": event.type.name,
                "payload": {
                    k: (str(v) if not isinstance(v, (int, float, str, bool, list, type(None))) else v)
                    for k, v in (event.payload or {}).items()
                },
                "source": str(event.source) if event.source else None,
            })
        except Exception:
            pass
        return original_emit(event)

    g.pipeline.emit = trace_emit
    try:
        g.combat_manager.declare_attack(a.id, 0)  # "Energy Drain"
    finally:
        g.pipeline.emit = original_emit

    fired, count, examples = _did_card_fire(
        captured, VOIDMAGE_APPRENTICE.fire_markers,
    )
    assert fired, (
        f"Trace must detect Voidmage's 'Energy Drain' as fired. Captured "
        f"{len(captured)} events; markers={sorted(VOIDMAGE_APPRENTICE.fire_markers)}"
    )
    assert count >= 1


# ---------------------------------------------------------------------------
# 4) Preflight self-check fires under deliberately-broken markers state
# ---------------------------------------------------------------------------


def test_preflight_check_passes_on_healthy_pipeline():
    """The preflight ``_preflight_marker_check`` is the trace's tripwire.
    On a healthy install (default markers + working pipeline) it must
    return without raising. This catches a broken refactor."""
    from scripts.play.brv_spice_event_trace import _preflight_marker_check
    _preflight_marker_check()  # should not raise


def test_preflight_check_raises_when_markers_are_wiped(monkeypatch):
    """Simulate a refactor regression: a card-factory bug or hand-edited
    override that wipes ``fire_markers``. The preflight must raise so
    downstream callers don't report bogus "0 firings"."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon import sv_starter
        from scripts.play.brv_spice_event_trace import _preflight_marker_check

    # Wipe Charmander's markers in-place. The preflight reads
    # CHARMANDER.fire_markers via the imported module, so monkeypatching
    # the attribute is sufficient. Restore via monkeypatch fixture.
    monkeypatch.setattr(sv_starter.CHARMANDER, "fire_markers", frozenset())

    with pytest.raises(RuntimeError, match="Preflight"):
        _preflight_marker_check()


def test_load_spice_fire_markers_returns_all_14_spice_cards():
    """Smoke test: the registry-walker loads markers for all 14 spice
    cards. If a spice card disappears from the BRV registry, this raises
    before the trace produces silently-wrong output."""
    from scripts.play.brv_spice_event_trace import (
        SPICE_CARD_NAMES, _load_spice_fire_markers,
    )

    markers = _load_spice_fire_markers()
    assert len(markers) == len(SPICE_CARD_NAMES)
    assert set(markers) == set(SPICE_CARD_NAMES)
    # Every card has at least its name as a marker.
    for name, m in markers.items():
        assert name in m, (
            f"Card {name!r} markers={sorted(m)} missing its own name"
        )


def test_spice_pokemon_markers_include_attack_names():
    """The original drift bug: Voidmage / Mirko / Aurelia source effects
    by attacker.id, so only their attack names appear in payloads. The
    auto-derived markers must include every spice Pokemon's attack
    names."""
    from scripts.play.brv_spice_event_trace import _load_spice_fire_markers

    markers = _load_spice_fire_markers()
    # The 14-card spice pack has 5 Pokemon: Mirko, Voidmage, Aurelia,
    # Obzedat, Jarad. Each must have its attack names auto-included.
    assert "Lost Recall" in markers["Mirko Vosk, Mind Drinker"]
    assert "Energy Drain" in markers["Voidmage Apprentice"]
    assert "Battalion Mark" in markers["Aurelia, the Warleader ex"]
    assert "Soul's Tax" in markers["Obzedat, Ghost Council ex"]
    assert "Spectral Decree" in markers["Obzedat, Ghost Council ex"]
    assert "Necrosurge" in markers["Jarad, Golgari Lich Lord ex"]
    assert "Lich's Bargain" in markers["Jarad, Golgari Lich Lord ex"]
