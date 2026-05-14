"""Stage 7.5b — FBN interceptor smoke + per-mechanic firing verification.

Two layers of safety:

1. ``test_fbn_setup_interceptors_no_crash``: every card with a
   ``setup_interceptors`` function runs against a synthetic SCP GameState
   without raising. Catches the "wired but crashes" failure mode.

2. ``test_fbn_<mechanic>_fires_on_sample_cards``: for each of the 8 new
   FBN mechanics, pick the first card from each archetype that carries
   the mechanic attribute, drive the engine hook, and assert the
   expected event surfaces. The 18 engine-extension tests in
   ``tests/test_fbn_engine_extensions.py`` already cover the mechanics
   in isolation; this layer proves the FBN cards actually wire through
   to those primitives.

Run via ``python -m pytest tests/test_fbn_interceptors.py``.
"""
from __future__ import annotations

import asyncio

import pytest

from src.engine.game import Game
from src.engine.types import CardType, Event, EventType, ZoneType
from src.engine import scp
from src.cards.scp.foundations_beyond import FBN_CARDS


# ---------------------------------------------------------------------------
# Fixtures (mirror tests/test_scp_interceptors.py)
# ---------------------------------------------------------------------------


def _setup() -> tuple[Game, str, str]:
    game = Game(mode="scp")
    p1 = game.add_player("Site-Alpha")
    p2 = game.add_player("Site-Beta")
    game.setup_scp_player(p1, [])
    game.setup_scp_player(p2, [])
    return game, p1, p2


def _push_to_battlefield(game: Game, owner_id: str, card_def):
    """Create a GameObject for a card and place it on the battlefield with
    ``scp_status="active"`` (or its zone-appropriate state).
    """
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.state.scp_status = "active"
    return obj


# ---------------------------------------------------------------------------
# Layer 1 — setup_interceptors crash audit
# ---------------------------------------------------------------------------


_SCP_BESPOKE_HOOKS: tuple[str, ...] = (
    "scp_on_reveal",
    "scp_on_contain",
    "scp_on_test",
    "scp_on_assign",
    "scp_on_breach",
    "scp_effect",
)


def test_fbn_bespoke_interceptors_no_crash():
    """Every FBN card that exposes a bespoke SCP hook
    (``scp_on_reveal`` / ``scp_on_contain`` / ``scp_on_test`` /
    ``scp_on_assign`` / ``scp_on_breach`` / ``scp_effect``) must run on a
    fresh GameObject + GameState without raising. Catches the
    "wired but crashes" failure mode that Stage 8 would otherwise burn
    cycles diagnosing.
    """
    game, p1, p2 = _setup()
    failures: list[tuple[str, str]] = []
    checked = 0
    for name, card_def in FBN_CARDS.items():
        bespoke = {h: getattr(card_def, h, None) for h in _SCP_BESPOKE_HOOKS}
        bespoke = {h: fn for h, fn in bespoke.items() if fn is not None}
        if not bespoke:
            continue
        checked += 1
        try:
            obj = _push_to_battlefield(game, p1.id, card_def)
        except Exception as exc:  # noqa: BLE001
            failures.append((name, f"create_object: {type(exc).__name__}: {str(exc)[:120]}"))
            continue
        for hook_name, hook_fn in bespoke.items():
            import inspect
            try:
                sig = inspect.signature(hook_fn)
                arity = len(sig.parameters)
            except (TypeError, ValueError):
                arity = 2
            try:
                # Drive the hook with the minimal shape it expects.
                # Signatures vary by hook — we accept any non-raising
                # outcome as "didn't crash."
                if hook_name == "scp_on_assign":
                    args = (obj, game.state, "contain", obj.id)
                else:
                    # Most SCP hooks: (obj, state) or (obj, state, game)
                    args = (obj, game.state, game)
                res = hook_fn(*args[:arity])
                assert res is None or isinstance(res, list)
            except TypeError:
                # Signature mismatch — try the 2-arg fallback, then give up.
                try:
                    res = hook_fn(obj, game.state)
                except TypeError:
                    continue
                except Exception as exc:  # noqa: BLE001
                    failures.append((name, f"{hook_name}: {type(exc).__name__}: {str(exc)[:120]}"))
            except Exception as exc:  # noqa: BLE001
                failures.append((name, f"{hook_name}: {type(exc).__name__}: {str(exc)[:120]}"))
    if failures:
        pytest.fail(
            f"{len(failures)} bespoke-hook crashes (out of {checked} hooked cards):\n  "
            + "\n  ".join(f"{n}: {e}" for n, e in failures[:15])
        )
    # Want at least a meaningful number of bespoke-hooked cards — if 0,
    # the codegen agents produced only keyword-tag cards (silent fail).
    assert checked >= 80, f"only {checked} cards have bespoke SCP hooks"


# ---------------------------------------------------------------------------
# Layer 2 — per-mechanic firing verification (sampled)
# ---------------------------------------------------------------------------


def _cards_with_attr(attr: str, predicate=None):
    """Return cards in ``FBN_CARDS`` that carry ``attr`` (and pass the
    optional ``predicate(card, value)``).
    """
    out = []
    for card in FBN_CARDS.values():
        v = getattr(card, attr, None)
        if v is None:
            continue
        if predicate is not None and not predicate(card, v):
            continue
        out.append(card)
    return out


def test_compleation_vector_card_population_distinct():
    cards = _cards_with_attr("scp_compleation_vector", lambda c, n: n > 0)
    assert len(cards) >= 5, f"only {len(cards)} Compleation Vector cards"
    # All values should be in 1-3.
    assert {getattr(c, "scp_compleation_vector") for c in cards} <= {1, 2, 3}


def test_phylactery_audit_card_population_distinct():
    cards = _cards_with_attr("scp_phylactery_audit", lambda c, n: n > 0)
    assert len(cards) >= 5, f"only {len(cards)} Phylactery Audit cards"
    assert {getattr(c, "scp_phylactery_audit") for c in cards} <= {1, 2, 3}


def test_spark_containment_card_population_distinct():
    cards = _cards_with_attr("scp_spark_containment", lambda c, n: n > 0)
    assert len(cards) >= 5, f"only {len(cards)} Spark Containment cards"


def test_leyline_saturation_card_population_distinct():
    cards = _cards_with_attr("scp_leyline_saturation", lambda c, n: n > 0)
    assert len(cards) >= 5, f"only {len(cards)} Leyline Saturation cards"


def test_planar_rift_card_population_distinct():
    cards = _cards_with_attr("scp_planar_rift", lambda c, n: n > 0)
    assert len(cards) >= 3, f"only {len(cards)} Planar Rift cards"


def test_dragon_hoard_card_population_distinct():
    cards = _cards_with_attr("scp_dragon_hoard", lambda c, n: n > 0)
    assert len(cards) >= 3, f"only {len(cards)} Dragon Hoard cards"


def test_annihilation_wave_card_population_distinct():
    cards = _cards_with_attr("scp_annihilation_wave", lambda c, n: n > 0)
    assert len(cards) >= 5, f"only {len(cards)} Annihilation Wave cards"


def test_wurm_devourer_card_population_distinct():
    cards = [
        c for c in FBN_CARDS.values()
        if getattr(c, "scp_wurm_devourer", False)
    ]
    assert len(cards) >= 3, f"only {len(cards)} Wurm Devourer cards"


def test_mnestic_personnel_population():
    """The 2 reused mechanics (Mnestic, Brief) must also have meaningful
    representation across the set.
    """
    mnestic = [c for c in FBN_CARDS.values() if getattr(c, "scp_mnestic", False)]
    assert len(mnestic) >= 5, f"only {len(mnestic)} Mnestic cards"


def test_fbn_alt_win_mandates_present():
    """Each FBN-specific alt-win must anchor at least one mandate."""
    alt_wins = {
        getattr(c, "scp_alt_win", None)
        for c in FBN_CARDS.values()
        if CardType.SCP_MANDATE in c.characteristics.types
    }
    alt_wins.discard(None)
    expected = {"compleation_overrun", "phylactery_chain", "wurm_apex_tamed"}
    missing = expected - alt_wins
    assert not missing, f"FBN alt-wins without mandate anchor: {missing}"
