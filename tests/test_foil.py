"""
Foil cosmetic flag — distribution test.

Asserts that ``GameSession.add_cards_to_deck`` rolls roughly ``FOIL_RATE``
of cards as foil, using the per-state seeded RNG so the rate is
deterministic. Run with: ``python tests/test_foil.py``.
"""

import sys

sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import Game
from src.server.session import GameSession, FOIL_RATE
from src.cards.custom.lorwyn_custom import LORWYN_CUSTOM_CARDS


def _build_session(seed: int) -> tuple[GameSession, str]:
    game = Game(mode="mtg")
    game.state.rng_seed = seed
    player = game.add_player("P1")
    session = GameSession(id="t-foil", game=game, mode="bot_vs_bot")
    session.player_ids.append(player.id)
    return session, player.id


def test_foil_rate_in_distribution():
    """1000 cards into a library → foil count should be within ±3σ of FOIL_RATE."""
    session, pid = _build_session(seed=42)

    # Any card def works — foil is a per-instance flag, not per-card-name.
    sample_card = next(iter(LORWYN_CUSTOM_CARDS.values()))
    deck = [sample_card] * 1000
    session.add_cards_to_deck(pid, deck)

    library = session.game.state.zones[f"library_{pid}"]
    object_ids = library.objects
    foils = sum(1 for oid in object_ids if session.game.state.objects[oid].state.foil)

    expected = FOIL_RATE * 1000
    # 3σ for Binomial(1000, 0.1) ≈ 28.5. Use 40 to keep this flake-free
    # without masking gross regressions.
    margin = 40
    assert abs(foils - expected) < margin, (
        f"Expected ~{expected} foils ±{margin}, got {foils}/1000 "
        f"(rate {foils/10:.1f}% vs target {FOIL_RATE*100:.0f}%)"
    )
    print(f"PASS test_foil_rate_in_distribution: {foils}/1000 foils "
          f"({foils/10:.1f}% vs target {FOIL_RATE*100:.0f}%)")


def test_foil_count_is_deterministic_given_seed():
    """
    Two sessions with the same seed should produce the same foil COUNT.

    Per-position equality is not testable because ``shuffle_library`` uses the
    module-level ``random`` (not the seeded state RNG), so post-shuffle order
    is non-deterministic. The foil-roll RNG itself is seeded, so the number
    of foils rolled across N draws is deterministic.
    """
    sample_card = next(iter(LORWYN_CUSTOM_CARDS.values()))

    def _foil_count(seed: int) -> int:
        session, pid = _build_session(seed=seed)
        session.add_cards_to_deck(pid, [sample_card] * 500)
        return sum(
            1
            for oid in session.game.state.zones[f"library_{pid}"].objects
            if session.game.state.objects[oid].state.foil
        )

    count_a = _foil_count(seed=12345)
    count_b = _foil_count(seed=12345)
    assert count_a == count_b, (
        f"Same seed must produce identical foil count, got {count_a} vs {count_b}"
    )
    print(f"PASS test_foil_count_is_deterministic_given_seed (count={count_a})")


def test_foil_flows_through_serializer():
    """A foil GameObject should serialize with ``foil=True`` in CardData."""
    session, pid = _build_session(seed=42)
    sample_card = next(iter(LORWYN_CUSTOM_CARDS.values()))
    session.add_cards_to_deck(pid, [sample_card] * 50)

    library = session.game.state.zones[f"library_{pid}"]
    foil_obj = next(
        (session.game.state.objects[oid] for oid in library.objects
         if session.game.state.objects[oid].state.foil),
        None,
    )
    assert foil_obj is not None, "Expected at least one foil in 50 cards at 10% rate"

    card_data = session._serialize_card(foil_obj)
    assert card_data.foil is True, "CardData.foil should reflect ObjectState.foil"

    # Pick a non-foil object too
    non_foil_obj = next(
        (session.game.state.objects[oid] for oid in library.objects
         if not session.game.state.objects[oid].state.foil),
        None,
    )
    assert non_foil_obj is not None
    assert session._serialize_card(non_foil_obj).foil is False
    print("PASS test_foil_flows_through_serializer")


if __name__ == "__main__":
    test_foil_rate_in_distribution()
    test_foil_count_is_deterministic_given_seed()
    test_foil_flows_through_serializer()
    print("\nAll foil tests passed.")
