"""
Tests for the hybrid deckbuilder route (W3).

Covers:
1. Route returns the heuristic skeleton when polish=True but the LLM is offline.
   build_heuristic_deck is patched at the module path the route imports it from.
2. Polish payload validation: a good swap is applied, an off-color swap is dropped,
   and the sideboard is bounded to 15 cards / 4-of.

build_heuristic_deck does not exist in this worktree (W2's territory) — we patch
it. This keeps the W3 worktree decoupled.
"""

import sys
import types
from unittest.mock import patch, AsyncMock, PropertyMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.cards.set_registry import get_cards_in_set
from src.decks.deck import Deck, DeckEntry
from src.server.routes.deckbuilder import router as deckbuilder_router


# -----------------------------------------------------------------------------
# Test app: mount only the deckbuilder router so we don't need socketio or the
# full server lifespan. Mirrors src/server/main.py's mount path.
# -----------------------------------------------------------------------------

def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(deckbuilder_router, prefix="/api")
    return app


# -----------------------------------------------------------------------------
# Stub builder package: W3's worktree does not contain src/decks/heuristics
# yet (W2's slice). We register a minimal stub module on sys.modules so the
# lazy import inside the route succeeds; tests then patch the function on it.
# -----------------------------------------------------------------------------

def _ensure_stub_builder_module() -> None:
    if "src.decks.heuristics" not in sys.modules:
        pkg = types.ModuleType("src.decks.heuristics")
        pkg.__path__ = []  # mark as a package
        sys.modules["src.decks.heuristics"] = pkg

    if "src.decks.heuristics.builder" not in sys.modules:
        builder_mod = types.ModuleType("src.decks.heuristics.builder")

        def _placeholder(*args, **kwargs):  # pragma: no cover - patched in tests
            raise RuntimeError("build_heuristic_deck must be patched in tests")

        builder_mod.build_heuristic_deck = _placeholder
        sys.modules["src.decks.heuristics.builder"] = builder_mod


_ensure_stub_builder_module()


# -----------------------------------------------------------------------------
# Fixtures: a tiny but real-card-backed mono-red skeleton that the polish
# validator can sanity-check against the FDN pool.
# -----------------------------------------------------------------------------

def _build_mono_red_skeleton() -> Deck:
    """
    Build a 60-card mono-red skeleton using real FDN cards + Mountains.

    The exact card mix is irrelevant to the test logic; what matters is that:
    - At least one real red FDN card is included (so a same-color swap can land).
    - The skeleton is colors=['R'] for the color-identity validator.
    """
    fdn = get_cards_in_set("FDN")
    red_creatures = [
        name for name, card_def in fdn.items()
        if card_def.characteristics.colors
        and {col.value for col in card_def.characteristics.colors} == {"R"}
        and "CREATURE" in [t.name for t in card_def.characteristics.types]
    ]
    # Pick the first 4 deterministically.
    chosen = sorted(red_creatures)[:4]

    mainboard: list[DeckEntry] = []
    for name in chosen:
        mainboard.append(DeckEntry(card_name=name, quantity=4))
    # Pad to 36 nonland cards with whatever red card is left.
    pad_cards = [n for n in sorted(red_creatures) if n not in chosen][:5]
    for name in pad_cards:
        mainboard.append(DeckEntry(card_name=name, quantity=4))
    # Add 4 of one more to push total to 40 nonlands.
    if pad_cards:
        mainboard.append(DeckEntry(card_name=pad_cards[0] + "_unused", quantity=0))
    # 24 Mountains.
    mainboard.append(DeckEntry(card_name="Mountain", quantity=24))

    return Deck(
        name="Heuristic Mono-Red",
        archetype="Aggro",
        colors=["R"],
        description="Heuristic skeleton",
        mainboard=[e for e in mainboard if e.quantity > 0],
        sideboard=[],
    )


# -----------------------------------------------------------------------------
# Test 1: LLM unavailable → skeleton returned as-is, even with polish=True.
# -----------------------------------------------------------------------------

def test_hybrid_build_returns_skeleton_when_llm_unavailable():
    """
    With polish=True but Ollama offline, the route must short-circuit and
    return the deterministic heuristic skeleton with no swaps.
    """
    skeleton = _build_mono_red_skeleton()

    with patch(
        "src.decks.heuristics.builder.build_heuristic_deck",
        return_value=skeleton,
    ) as mock_builder, patch(
        "src.ai.llm.ollama_provider.OllamaProvider.is_available",
        new_callable=PropertyMock,
        return_value=False,
    ):
        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/api/deckbuilder/hybrid/build",
            json={
                "name": "Test Aggro",
                "archetype": "Aggro",
                "colors": ["R"],
                "set_codes": ["FDN"],
                "polish": True,
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["swaps"] == []
    assert data["deck"] is not None
    assert data["skeleton"] is not None
    # deck should equal skeleton dict when polish was skipped.
    assert data["deck"]["name"] == skeleton.name
    assert data["skeleton"]["name"] == skeleton.name
    assert data["deck"]["mainboard_count"] == skeleton.mainboard_count

    # Builder must have been called with the requested args.
    mock_builder.assert_called_once()
    call_kwargs = mock_builder.call_args.kwargs
    assert call_kwargs["archetype"] == "Aggro"
    assert call_kwargs["colors"] == ["R"]
    assert call_kwargs["set_codes"] == ["FDN"]


# -----------------------------------------------------------------------------
# Test 2: polish payload — the in-color swap is applied; the off-color swap is
# rejected. Sideboard with one >4 entry is clamped.
# -----------------------------------------------------------------------------

def test_hybrid_build_drops_off_color_swap_and_applies_valid_swap():
    """
    LLM returns:
      - a valid same-color swap (Mountain-flavor red -> red)
      - an off-color swap (a green card the validator must drop)
      - a sideboard entry with qty=8 that must clamp to 4
    Assert: swaps list contains exactly the in-color swap; off-color one absent.
    """
    skeleton = _build_mono_red_skeleton()

    fdn = get_cards_in_set("FDN")
    # Find a valid in-color replacement: a red card NOT in the skeleton.
    skeleton_names = {e.card_name for e in skeleton.mainboard}
    in_color_choice = None
    for name, card_def in sorted(fdn.items()):
        if name in skeleton_names:
            continue
        cols = {c.value for c in card_def.characteristics.colors or set()}
        if cols == {"R"}:
            in_color_choice = name
            break
    assert in_color_choice is not None, "FDN should have at least one mono-red replacement"

    # Find an off-color (green) card present in FDN.
    off_color_choice = None
    for name, card_def in sorted(fdn.items()):
        cols = {c.value for c in card_def.characteristics.colors or set()}
        if cols == {"G"}:
            off_color_choice = name
            break
    assert off_color_choice is not None, "FDN should have a mono-green card to test rejection"

    # Pick the "out" card: the first non-Mountain skeleton entry.
    out_card = next(e for e in skeleton.mainboard if e.card_name != "Mountain")

    # Pick a sideboard candidate (any red card from FDN with qty=8 to test clamping).
    sb_card = None
    for name, card_def in sorted(fdn.items()):
        cols = {c.value for c in card_def.characteristics.colors or set()}
        if cols == {"R"}:
            sb_card = name
            break

    polish_payload = {
        "name": "Brutal Mono-Red Tempest",
        "description": "Fast hands burn fast.",
        "swaps": [
            {
                "out": out_card.card_name,
                "in": in_color_choice,
                "qty": 1,
                "reason": "Better curve filler",
            },
            {
                "out": out_card.card_name,
                "in": off_color_choice,
                "qty": 1,
                "reason": "Splashing green is fine right? (should be dropped)",
            },
        ],
        "sideboard": [
            {"card": sb_card, "qty": 8},  # over 4-of -> clamped to 4
        ],
    }

    async def _fake_complete_json(*args, **kwargs):
        return polish_payload

    with patch(
        "src.decks.heuristics.builder.build_heuristic_deck",
        return_value=skeleton,
    ), patch(
        "src.ai.llm.ollama_provider.OllamaProvider.is_available",
        new_callable=PropertyMock,
        return_value=True,
    ), patch(
        "src.ai.llm.ollama_provider.OllamaProvider.complete_json",
        new=AsyncMock(side_effect=_fake_complete_json),
    ):
        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/api/deckbuilder/hybrid/build",
            json={
                "name": "Test Aggro",
                "archetype": "Aggro",
                "colors": ["R"],
                "set_codes": ["FDN"],
                "polish": True,
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["success"] is True
    assert data["deck"] is not None
    assert data["skeleton"] is not None

    swaps = data["swaps"]
    assert len(swaps) == 1, f"Expected exactly one accepted swap, got: {swaps}"
    accepted = swaps[0]
    assert accepted["in"] == in_color_choice
    assert accepted["out"] == out_card.card_name
    # The off-color "in" must not appear anywhere in the accepted swaps.
    assert all(s["in"] != off_color_choice for s in swaps)

    # Polished deck must reflect the accepted swap.
    polished_names = {e["card"]: e["qty"] for e in data["deck"]["mainboard"]}
    assert in_color_choice in polished_names
    assert polished_names[in_color_choice] >= 1
    # Out card should have been decremented by one copy.
    assert polished_names.get(out_card.card_name, 0) == out_card.quantity - 1
    # Off-color card must NOT be in the polished mainboard.
    assert off_color_choice not in polished_names

    # Sideboard validation: clamped to 4 (input was 8) and total <= 15.
    sb = data["deck"]["sideboard"]
    assert len(sb) == 1
    assert sb[0]["card"] == sb_card
    assert sb[0]["qty"] == 4
    assert sum(e["qty"] for e in sb) <= 15

    # Skeleton in response is the pre-polish snapshot.
    assert data["skeleton"]["name"] == skeleton.name


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
