"""Regression guard for the SCP path of scripts/play/diagnose_card_fire.py (/card-fire-debug).

This path bit-rotted silently once already: when the symmetric "SCP-1" engine was deleted on
2026-05-31 the probe kept importing ``src.engine.scp_abilities`` / ``scp_tournament.SCP_STARTER_DECKS``
and calling ``game.setup_scp_player(p, deck)`` — all gone — so ``/card-fire-debug`` crashed on every
SCP card with ``ModuleNotFoundError``. It went unnoticed for ~9 months because the only coverage lived
in tests/test_card_fire_debug.py, which is skipped under pytest (manual-run only). This file is
collected by pytest so the live-engine wiring can't break unnoticed again.

It is deliberately cheap: instant synthetic checks of the decision tree + a couple of short real
self-play games to prove the probe still wires to the asymmetric engine end-to-end.

Run: PYTHONPATH=. python3 -m pytest tests/test_scp_card_fire.py -q
"""

import asyncio

import pytest

from scripts.play.diagnose_card_fire import (
    CardTelemetry,
    _resolve_engine,
    _resolve_scp_matchup,
    _run_scp_diagnostic_game,
    diagnose_scp,
)

# A core Foundation anomaly the install→advance→contain loop plays every game; site19 runs 3 of it.
PROBE_CARD = "SCP-0863 Anomalous Specimen"
FOUNDATION_DECK = "SCP_site19_containment"
INSURGENCY_DECK = "SCP_black_queen_cell"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _tele(**kw) -> CardTelemetry:
    t = CardTelemetry(card_name="Synthetic", games_run=3)
    for k, v in kw.items():
        setattr(t, k, v)
    return t


# --------------------------------------------------------------------------- decision tree (instant)
def test_diagnose_scp_step0_not_in_deck():
    steps, verdict, _ = diagnose_scp(_tele(deck_count_p1=0, deck_count_p2=0))
    assert verdict == "FAIL"
    assert steps[0].name.startswith("Step 0") and not steps[0].passed


def test_diagnose_scp_step1_never_drawn():
    steps, verdict, _ = diagnose_scp(_tele(deck_count_p1=2, drawn_count=0))
    assert verdict == "FAIL"
    assert any(s.name.startswith("Step 1") and not s.passed for s in steps)


def test_diagnose_scp_step2_drawn_but_never_played():
    steps, verdict, patch = diagnose_scp(
        _tele(deck_count_p1=2, drawn_count=6, scp_kind="OPERATION", scp_times_played=0)
    )
    assert verdict == "FAIL"
    assert "never plays" in patch.lower()  # the level-3 (AI-dead) diagnosis


def test_diagnose_scp_no_ability_played_is_fire():
    _, verdict, _ = diagnose_scp(
        _tele(deck_count_p1=3, drawn_count=6, scp_kind="ANOMALY",
              scp_times_played=4, scp_has_ability=False)
    )
    assert verdict == "PASS"


def test_diagnose_scp_ability_played_and_activated():
    _, verdict, _ = diagnose_scp(
        _tele(deck_count_p1=1, drawn_count=6, scp_kind="ASSET", scp_has_ability=True,
              scp_times_played=2, scp_times_activated=2)
    )
    assert verdict == "PASS"


def test_diagnose_scp_ability_installed_but_dormant_warns():
    # The Site-Director-style case the restored probe surfaces: installed, ability never fired.
    _, verdict, patch = diagnose_scp(
        _tele(deck_count_p1=1, drawn_count=6, scp_kind="ASSET", scp_has_ability=True,
              scp_times_played=2, scp_times_activated=0)
    )
    assert verdict == "WARN"
    assert "activate" in patch.lower()


# --------------------------------------------------------------------------- matchup / engine resolve
def test_resolve_engine_detects_scp_from_deck_name():
    assert _resolve_engine(None, FOUNDATION_DECK) == "scp"
    assert _resolve_engine(None, INSURGENCY_DECK) == "scp"


def test_resolve_scp_matchup_orders_factions_either_way():
    assert _resolve_scp_matchup(FOUNDATION_DECK, INSURGENCY_DECK) == (FOUNDATION_DECK, INSURGENCY_DECK)
    # order-independent: foundation is always returned first
    assert _resolve_scp_matchup(INSURGENCY_DECK, FOUNDATION_DECK) == (FOUNDATION_DECK, INSURGENCY_DECK)


def test_resolve_scp_matchup_rejects_same_faction():
    with pytest.raises(SystemExit, match="asymmetric"):
        _resolve_scp_matchup(FOUNDATION_DECK, "SCP_dr_light")  # two Foundation decks


def test_resolve_scp_matchup_rejects_unknown_deck():
    with pytest.raises(SystemExit, match="Unknown SCP deck"):
        _resolve_scp_matchup(FOUNDATION_DECK, "SCP_not_a_real_deck")


# --------------------------------------------------------------------------- live-engine wiring (cheap)
def test_probe_runs_on_live_engine_and_counts_deck_presence():
    """One short game must run end-to-end (catches import / signature rot) and see the 3 copies."""
    tele = _run(_run_scp_diagnostic_game(
        card_name=PROBE_CARD, p1_deck_name=FOUNDATION_DECK, p2_deck_name=INSURGENCY_DECK,
        difficulty="medium", max_turns=60, seed=1,
    ))
    assert tele.games_run == 1
    assert tele.deck_count_p1 == 3  # site19 runs 3 Anomalous Specimen
    assert tele.deck_count_p2 == 0
    assert tele.scp_kind == "SCP_ANOMALY"


def test_probe_core_anomaly_fires_under_heuristic_ai():
    """Across a short multi-game sample the Foundation install loop plays its densest (x3)
    anomaly, the probe attributes those SCP_INSTALL events to it, and the verdict is PASS.

    Sampled over 8 seeds for a comfortable margin — per-game play is lumpy (some seeds install
    it 0 times, others 1-2), so this only fails if the AI essentially stops playing its densest
    anomaly across the whole sample (a real regression) or the probe's attribution breaks, not
    on incidental per-seed RNG drift.
    """
    agg = CardTelemetry(card_name=PROBE_CARD)
    for seed in range(8):
        agg.merge(_run(_run_scp_diagnostic_game(
            card_name=PROBE_CARD, p1_deck_name=FOUNDATION_DECK, p2_deck_name=INSURGENCY_DECK,
            difficulty="medium", max_turns=80, seed=seed,
        )))
    _, verdict, _ = diagnose_scp(agg)
    assert agg.scp_times_played > 0, "densest anomaly never played across 8 games — probe or AI broke"
    assert verdict == "PASS"


def test_probe_normalizes_pokemon_default_difficulty():
    """The script-wide default difficulty is the Pokemon-centric 'balanced'; the SCP probe must
    normalize it to a valid scp tier instead of raising ValueError out of SCPAIAdapter."""
    tele = _run(_run_scp_diagnostic_game(
        card_name=PROBE_CARD, p1_deck_name=FOUNDATION_DECK, p2_deck_name=INSURGENCY_DECK,
        difficulty="balanced", max_turns=20, seed=0,
    ))
    assert tele.games_run == 1  # ran without raising


def test_probe_missing_card_reports_step0_fail():
    tele = _run(_run_scp_diagnostic_game(
        card_name="Totally Made Up SCP 999", p1_deck_name=FOUNDATION_DECK,
        p2_deck_name=INSURGENCY_DECK, difficulty="medium", max_turns=8, seed=0,
    ))
    steps, verdict, _ = diagnose_scp(tele)
    assert verdict == "FAIL"
    assert steps[0].name.startswith("Step 0") and not steps[0].passed


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
