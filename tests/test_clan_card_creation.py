"""CLAN card-creation smoke test (Stage-4 reconciliation canary).

For every card in ``src.cards.clankers.CLAN.CLAN_CARDS`` this test verifies:
  1. The card can be turned into a ``GameObject`` via ``Game.create_object``
     in the appropriate zone (COMMAND for Cores, HAND for Transients,
     CLANKERS_ASSEMBLY_FLOOR for chassis/parts/structures).
  2. If the card has a ``setup_interceptors`` function, ``create_object``
     ran it without raising an exception.

This is the canary that catches drift between the four parallel archetype
agents (FORGE / ETHOS / MIRTH / BULWARK). It must pass cleanly — any crash
indicates the agent shipped a card whose setup_interceptors blows up on
construction (typo, missing import, signature mismatch with the engine).

Run directly:
    python tests/test_clan_card_creation.py
"""

from __future__ import annotations

from src.cards.clankers.CLAN import CLAN_CARDS
from src.engine.clankers import _init_clankers_state
from src.engine.game import Game
from src.engine.types import CardType, Player, Zone, ZoneType


def _build_minimal_game() -> Game:
    """Build a two-player Game with all per-player Clankers zones initialised.

    We don't run the full ``setup_clankers_player`` here — we just need the
    zone keys to exist so ``Game.create_object`` can append into them.
    """
    g = Game()
    g.state.players["p1"] = Player(id="p1", name="p1")
    g.state.players["p2"] = Player(id="p2", name="p2")
    per_player_zones = (
        ZoneType.HAND,
        ZoneType.COMMAND,
        ZoneType.LIBRARY,
        ZoneType.CLANKERS_ASSEMBLY_FLOOR,
        ZoneType.CLANKERS_SCRAP_HEAP,
    )
    for pid in ("p1", "p2"):
        for zt in per_player_zones:
            key = f"{zt.name.lower()}_{pid}"
            if key not in g.state.zones:
                g.state.zones[key] = Zone(type=zt, owner=pid)

    _init_clankers_state(g.state)
    # Seed per-player slots so any setup_interceptors that read them
    # (e.g. compute pool, workshop integrity) don't trip on KeyError.
    for pid in ("p1", "p2"):
        g.state.clankers_workshop_integrity[pid] = 25
        g.state.clankers_compute_pool[pid] = 10
        g.state.clankers_compute_cap[pid] = 10
        g.state.clankers_scrap_pool[pid] = 0
        g.state.clankers_refill_used[pid] = False
        g.state.clankers_structures[pid] = []
        g.state.clankers_assemblies[pid] = []
    return g


def _zone_for(card_def) -> ZoneType:
    """Decide which zone to drop a card into.

    Cores live in COMMAND, Transients live in HAND (they resolve on play
    and never sit on the floor), everything else lives on the Assembly
    Floor (chassis, parts, structures).
    """
    if card_def.characteristics is None or not card_def.characteristics.types:
        return ZoneType.HAND
    types = card_def.characteristics.types
    if CardType.CLANKERS_CORE in types:
        return ZoneType.COMMAND
    if CardType.CLANKERS_TRANSIENT in types:
        return ZoneType.HAND
    return ZoneType.CLANKERS_ASSEMBLY_FLOOR


def test_clan_cards_create_without_raising() -> None:
    """Every CLAN card must construct + register setup_interceptors cleanly."""
    g = _build_minimal_game()
    failures: list[tuple[str, str, str]] = []
    created = 0

    for dict_key, card_def in CLAN_CARDS.items():
        zone = _zone_for(card_def)
        try:
            obj = g.create_object(
                name=card_def.name,
                owner_id="p1",
                zone=zone,
                characteristics=card_def.characteristics,
                card_def=card_def,
            )
            assert obj is not None, f"create_object returned None for {dict_key}"
            assert obj.card_def is card_def, (
                f"card_def not attached for {dict_key}"
            )
            created += 1
        except Exception as exc:  # pragma: no cover - test fails on exception
            failures.append((dict_key, card_def.name, f"{type(exc).__name__}: {exc}"))

    assert not failures, (
        f"{len(failures)} CLAN card(s) failed to create/setup:\n  "
        + "\n  ".join(f"{k} ({n}): {e}" for k, n, e in failures)
    )
    assert created == len(CLAN_CARDS), (
        f"Created {created} of {len(CLAN_CARDS)} CLAN cards"
    )


def test_clan_cards_count() -> None:
    """Sanity check: CLAN ships exactly 151 cards (Stage-4 baseline)."""
    assert len(CLAN_CARDS) == 151, (
        f"CLAN_CARDS contains {len(CLAN_CARDS)} cards; expected 151"
    )


def test_clan_card_names_distinct_in_dict() -> None:
    """No two dict keys collide (the merge in __init__.py would silently
    drop the second). Also confirm any duplicate printed names are
    intentional (Affection.exe Core vs Affection.exe Add-On)."""
    keys = list(CLAN_CARDS.keys())
    assert len(keys) == len(set(keys)), "Duplicate dict keys in CLAN_CARDS"

    # Printed-name duplicates are flagged but allowed if the design doc
    # intentionally reuses a name (Affection.exe Core / Add-On).
    from collections import Counter
    names = [cd.name for cd in CLAN_CARDS.values()]
    dupes = {n: c for n, c in Counter(names).items() if c > 1}
    allowed = {"Affection.exe"}  # design doc § 345 + § 521
    unexpected = {n: c for n, c in dupes.items() if n not in allowed}
    assert not unexpected, (
        f"Unexpected printed-name duplicates in CLAN_CARDS: {unexpected}"
    )


if __name__ == "__main__":
    test_clan_cards_create_without_raising()
    test_clan_cards_count()
    test_clan_card_names_distinct_in_dict()
    print(f"OK: {len(CLAN_CARDS)} CLAN cards create cleanly.")
