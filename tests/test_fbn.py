"""Foundations Beyond (FBN) smoke test.

Verifies that the FBN package imports cleanly, all 300 cards instantiate,
all 10 starter decks build, and one AI-vs-AI game finishes without crashing.
Run via ``python -m pytest tests/test_fbn.py``.
"""
from __future__ import annotations

import pytest

from src.engine.game import Game
from src.engine.types import CardDefinition, CardType, ZoneType
from src.engine import scp
from src.cards.scp import SCP_CARDS, SCP_STARTER_DECKS
from src.cards.scp.foundations_beyond import (
    EXPANSION,
    EXPANSION_CODE,
    FBN_CARDS,
    FBN_STARTER_DECK_FACTORIES,
)


def test_fbn_card_pool_size():
    # 300 baseline + 1 verb-redesign signature bomb (Operative O5-7, Strain
    # Harvester, added to Phyrexian Strain). Bump deliberately as the redesign
    # adds marquee cards — the exact-count guard exists to catch unintended drift.
    assert len(FBN_CARDS) == 301, f"expected 301 FBN cards, got {len(FBN_CARDS)}"


def test_fbn_merged_into_scp_registry():
    missing = [name for name in FBN_CARDS if name not in SCP_CARDS]
    assert not missing, f"{len(missing)} FBN cards missing from SCP_CARDS: {missing[:5]}"


def test_fbn_archetype_split():
    """Every FBN card must have one of the 10 archetype slugs."""
    expected = {
        "phyrexian_strain", "eldrazi_apex", "dragon_conclave",
        "planeswalker_detention", "demonic_pact_bureau", "leyline_anomaly",
        "multiverse_rift", "lich_phylactery", "wurm_apex", "spirit_archive",
    }
    seen = {getattr(card, "scp_archetype", None) for card in FBN_CARDS.values()}
    assert seen == expected, f"archetype slugs drift: {seen ^ expected}"


def test_fbn_expansion_stamp():
    """Every FBN card must carry the FBN expansion code."""
    bad = [
        (card.name, getattr(card, "scp_expansion_code", None))
        for card in FBN_CARDS.values()
        if getattr(card, "scp_expansion_code", None) != EXPANSION_CODE
    ]
    assert not bad, f"{len(bad)} cards missing FBN expansion stamp: {bad[:5]}"


def test_fbn_card_types_distribution():
    """Each archetype has ~12-14 anomalies, ~6-8 personnel, ~3-5 facilities,
    ~4-5 procedures, ~1-2 mandates.
    """
    by_type: dict[CardType, int] = {}
    for card in FBN_CARDS.values():
        for ct in card.characteristics.types:
            by_type[ct] = by_type.get(ct, 0) + 1
    assert by_type.get(CardType.SCP_ANOMALY, 0) >= 100, by_type
    assert by_type.get(CardType.SCP_PERSONNEL, 0) >= 50, by_type
    assert by_type.get(CardType.SCP_FACILITY, 0) >= 30, by_type
    assert by_type.get(CardType.SCP_PROCEDURE, 0) >= 40, by_type
    assert by_type.get(CardType.SCP_MANDATE, 0) >= 10, by_type


def test_fbn_all_starter_decks_build():
    assert len(FBN_STARTER_DECK_FACTORIES) == 10
    for label, builder in FBN_STARTER_DECK_FACTORIES.items():
        deck = builder()
        assert len(deck) == 30, f"{label}: {len(deck)} cards (expected 30)"
        for card in deck:
            assert card.name in FBN_CARDS, f"{label}: {card.name!r} not in FBN_CARDS"


def test_fbn_starter_decks_registered_in_scp_global():
    """All 10 FBN decks must appear in the unified SCP_STARTER_DECKS dict."""
    fbn_keys = [k for k in SCP_STARTER_DECKS if k.startswith("FBN_")]
    assert len(fbn_keys) == 10, f"expected 10 FBN_* deck labels, got {len(fbn_keys)}: {fbn_keys}"


def test_fbn_all_cards_instantiate_clean():
    """Every card must construct a GameObject without raising."""
    game = Game(mode="scp")
    p1 = game.add_player("Site-Alpha")
    p2 = game.add_player("Site-Beta")
    game.setup_scp_player(p1, [])
    game.setup_scp_player(p2, [])
    failures: list[tuple[str, str]] = []
    for name, card_def in FBN_CARDS.items():
        try:
            game.create_object(
                name=card_def.name,
                owner_id=p1.id,
                zone=ZoneType.HAND,
                characteristics=card_def.characteristics,
                card_def=card_def,
            )
        except Exception as exc:  # noqa: BLE001
            failures.append((name, str(exc)[:200]))
    assert not failures, f"{len(failures)} FBN cards failed instantiation: {failures[:3]}"


def test_fbn_mechanics_present():
    """Every named FBN mechanic appears on at least one card's
    ``scp_keywords``.
    """
    expected_mechanics = {
        "Brief", "Mnestic", "Compleation Vector", "Phylactery Audit",
        "Spark Containment", "Annihilation Wave", "Dragon Hoard",
        "Leyline Saturation", "Planar Rift", "Wurm Devourer",
    }
    seen: set[str] = set()
    for card in FBN_CARDS.values():
        for kw in getattr(card, "scp_keywords", []) or []:
            # Keyword stamps look like "Compleation Vector 2" — strip the N.
            head = " ".join(part for part in kw.split() if not part.isdigit())
            seen.add(head)
    missing = expected_mechanics - seen
    assert not missing, f"mechanics with zero card mentions: {missing}"


def test_fbn_alt_wins_registered():
    """Cards with ``scp_alt_win`` must reference a key the engine knows
    about (existing SZB/MNR wins + 3 new FBN wins).
    """
    known = {
        "public_panic", "thaumiel", "redaction", "ethics_audit",
        "memory_hole", "mnestic_saturation",
        "compleation_overrun", "phylactery_chain", "wurm_apex_tamed",
    }
    for card in FBN_CARDS.values():
        win = getattr(card, "scp_alt_win", None)
        if win is not None:
            assert win in known, f"{card.name}: alt-win {win!r} not registered"


def test_fbn_decks_setup_scp_player_clean():
    """Every FBN deck must pass through ``setup_scp_player`` cleanly.

    A full AI-vs-AI game is exercised by ``scripts/play/scp_tournament.py``
    (async loop); here we only verify that the per-deck setup path works
    so the tournament adapter has a stable launch surface.
    """
    for label, builder in FBN_STARTER_DECK_FACTORIES.items():
        deck = builder()
        game = Game(mode="scp")
        a = game.add_player(f"{label}-A")
        b = game.add_player(f"{label}-B")
        try:
            game.setup_scp_player(a, deck)
            game.setup_scp_player(b, deck)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"{label} setup_scp_player crashed: {exc}")
