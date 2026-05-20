"""Tests for ``src/ai/cats_llm_adapter.py``.

We do NOT call the real `claude` CLI. The provider's ``complete_json`` method
is monkeypatched to return a fixed dict (or raise) per test. This keeps the
test suite hermetic and fast.

Tests:
    test_llm_adapter_constructs
        — Adapter constructs without the CLI being available.
    test_llm_adapter_returns_valid_choice
        — When the (mocked) provider returns a valid slot, ``choose_card``
          returns the corresponding card_id from ``available_card_ids``.
    test_llm_adapter_fallback_on_error
        — When the (mocked) provider raises, the adapter falls back to the
          heuristic medium and still returns one of the legal card_ids.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ai.cats_llm_adapter import CatsLLMAdapter


# ---------------------------------------------------------------------------
# Fixtures: a real-ish game state with two players + hands.
# ---------------------------------------------------------------------------

def _build_state():
    """Build a minimal cats game state with hands + commanders.

    Uses the real setup_cats_player so the state has all the fields the
    adapter expects (cats_round_number, cats_piles, HAND zones, objects).
    """
    from src.engine.cats import setup_cats_player
    from src.engine.types import GameState, Player
    from src.cards.cats.CATS import CATS_LIST, MOODS, SNACKS, TRINKETS, COMMANDERS

    state = GameState()
    state.game_mode = "cats"
    state.rng_seed = 42
    state.players["p1"] = Player(id="p1", name="P1")
    state.players["p2"] = Player(id="p2", name="P2")

    # Build a 30-card deck for each player. Deterministic via Random(42).
    rng = random.Random(42)
    deck1 = (
        rng.choices(CATS_LIST, k=18)
        + rng.choices(MOODS, k=6)
        + rng.choices(SNACKS, k=4)
        + rng.choices(TRINKETS, k=2)
    )
    rng.shuffle(deck1)
    deck2 = (
        rng.choices(CATS_LIST, k=18)
        + rng.choices(MOODS, k=6)
        + rng.choices(SNACKS, k=4)
        + rng.choices(TRINKETS, k=2)
    )
    rng.shuffle(deck2)

    setup_cats_player(state, "p1", deck1, commander=COMMANDERS[0])
    setup_cats_player(state, "p2", deck2, commander=COMMANDERS[1])
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_llm_adapter_constructs():
    """The adapter constructs even if `claude` CLI is missing.

    The provider's ``is_available`` is False on a machine without the CLI,
    but construction shouldn't fail — we only shell out at decision time.
    """
    a = CatsLLMAdapter(model="haiku")
    assert a.player_id is None
    assert a.model == "haiku"
    assert a.verbose is False
    assert a.decisions == []
    # Construct with verbose=True too — must not raise.
    b = CatsLLMAdapter(model="sonnet", verbose=True, timeout=10.0)
    assert b.verbose is True
    assert b.provider.timeout == 10.0


def test_llm_adapter_returns_valid_choice_with_mock(monkeypatch):
    """When the provider returns a valid slot, the adapter resolves it.

    We monkeypatch the provider's ``complete_json`` coroutine to return a
    fixed dict (slot=2 of the 3-card hand). The adapter should return the
    card_id at index 1 of ``available_card_ids``.
    """
    state = _build_state()
    adapter = CatsLLMAdapter(model="haiku")
    adapter.player_id = "p1"

    # Grab the p1 hand — the engine populated it during setup_cats_player.
    hand_zone = state.zones[f"HAND_p1"]
    hand_ids = list(hand_zone.objects)
    assert len(hand_ids) >= 3, "expected setup_cats_player to deal a 5-card hand"

    # Slice to 3 cards so the slot mapping is unambiguous.
    available = hand_ids[:3]

    captured_prompts = []

    async def fake_complete_json(prompt, schema, system=None, temperature=0.1):
        captured_prompts.append(prompt)
        return {"slot": 2, "reasoning": "playing the middle card for predictability"}

    monkeypatch.setattr(adapter.provider, "complete_json", fake_complete_json)

    chosen = adapter.choose_card(state, available)
    assert chosen == available[1], (
        f"expected the slot-2 card ({available[1]!r}), got {chosen!r}"
    )

    # Adapter should have logged the decision.
    assert len(adapter.decisions) == 1
    rec = adapter.decisions[0]
    assert rec["type"] == "choose_card"
    assert rec["chosen"] == available[1]
    assert rec["result"]["slot"] == 2

    # The prompt should mention card names + slot numbers + the player seat.
    assert captured_prompts, "provider was never called"
    prompt = captured_prompts[0]
    assert "round" in prompt.lower()
    assert "slot" in prompt.lower() or "1." in prompt
    assert "p1" in prompt


def test_llm_adapter_fallback_on_error(monkeypatch):
    """When the provider errors, the adapter returns a legal card via the heuristic."""
    state = _build_state()
    adapter = CatsLLMAdapter(model="haiku")
    adapter.player_id = "p1"

    hand_zone = state.zones[f"HAND_p1"]
    hand_ids = list(hand_zone.objects)
    assert len(hand_ids) >= 2

    async def fake_complete_json(prompt, schema, system=None, temperature=0.1):
        raise RuntimeError("simulated CLI timeout")

    monkeypatch.setattr(adapter.provider, "complete_json", fake_complete_json)

    chosen = adapter.choose_card(state, hand_ids)
    # Heuristic medium returned a card from the legal set.
    assert chosen in hand_ids, (
        f"fallback returned {chosen!r} which isn't in the legal hand"
    )
    # No decision was logged (we only log successful LLM calls).
    assert adapter.decisions == []


def test_llm_adapter_pile_choice_with_mock(monkeypatch):
    """choose_pile maps a returned pile string to one of the available_pile_names."""
    state = _build_state()
    adapter = CatsLLMAdapter(model="haiku")
    adapter.player_id = "p1"

    available = ["pile_territory", "pile_nap", "pile_snack"]
    won_ids: list[str] = []

    async def fake_complete_json(prompt, schema, system=None, temperature=0.1):
        return {"pile": "pile_snack", "reasoning": "snack is 3pt/card if pile is small"}

    monkeypatch.setattr(adapter.provider, "complete_json", fake_complete_json)

    chosen = adapter.choose_pile(state, won_ids, available)
    assert chosen == "pile_snack"
    assert len(adapter.decisions) == 1
    assert adapter.decisions[0]["type"] == "choose_pile"


def test_llm_adapter_pile_choice_accepts_short_name(monkeypatch):
    """If the LLM returns 'snack' rather than 'pile_snack' we still resolve it."""
    state = _build_state()
    adapter = CatsLLMAdapter(model="haiku")
    adapter.player_id = "p1"

    available = ["pile_territory", "pile_nap", "pile_snack"]

    async def fake_complete_json(prompt, schema, system=None, temperature=0.1):
        return {"pile": "snack", "reasoning": "short-name version"}

    monkeypatch.setattr(adapter.provider, "complete_json", fake_complete_json)

    chosen = adapter.choose_pile(state, [], available)
    assert chosen == "pile_snack", f"short-name 'snack' should map to 'pile_snack', got {chosen!r}"


def test_llm_adapter_choose_activations_returns_empty():
    """v1 punts activations — must return [] not None / not a dataclass."""
    state = _build_state()
    adapter = CatsLLMAdapter()
    adapter.player_id = "p1"
    result = adapter.choose_activations(state)
    assert result == []
    assert isinstance(result, list)


def test_llm_adapter_invalid_slot_falls_back(monkeypatch):
    """If the LLM returns a slot outside 1..N, the adapter falls back."""
    state = _build_state()
    adapter = CatsLLMAdapter()
    adapter.player_id = "p1"

    hand_zone = state.zones[f"HAND_p1"]
    available = list(hand_zone.objects)[:3]

    async def fake_complete_json(prompt, schema, system=None, temperature=0.1):
        return {"slot": 99, "reasoning": "out of range"}

    monkeypatch.setattr(adapter.provider, "complete_json", fake_complete_json)

    chosen = adapter.choose_card(state, available)
    assert chosen in available, "out-of-range slot should fall back to heuristic"
