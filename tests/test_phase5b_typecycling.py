"""Phase 5b sweep — typecycling wirings (Agent T1).

Lightweight smoke tests confirming the 5 typecycling cards from the
2026-05-16 strict-noop audit have their cycling activated ability
registered via ``setup_in_hand = make_cycling_setup(...)`` on the
engine's official cycling path (src/engine/cycling.py).

Each test:
    1. Creates the card in HAND (so the pipeline's HAND-zone hook runs
       setup_in_hand).
    2. Asserts an ActivatedAbility with cost_text containing
       "{2}, Discard this card" is registered on the object.
    3. Asserts the description mentions the expected land subtype, so
       a future agent who accidentally swaps the typecycling target
       won't silently regress.

Coverage:
    DSK — Shepherding Spirits     (Plainscycling {2})
    DSK — Daggermaw Megalodon     (Islandcycling {2})
    DSK — Bedhead Beastie         (Mountaincycling {2})
    DSK — Slavering Branchsnapper (Forestcycling {2})
    TLA — Saber-Tooth Moose-Lion  (Forestcycling {2})

Resolution of the SEARCH_LIBRARY PendingChoice is out of scope here —
these tests verify the descriptor is wired up correctly.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import Game, ZoneType


# =============================================================================
# Helpers
# =============================================================================

def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put_in_hand(game, owner, card_def):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _find_cycling_ability(obj, *, expected_subtype: str):
    """Return the cycling ActivatedAbility, or None if missing.

    Match criteria:
        - cost_text contains "{2}, Discard this card" (case-insensitive)
        - description mentions the expected subtype
    """
    expected_cost = "{2}, discard this card"
    abilities = getattr(obj.state, "activated_abilities", None) or []
    for a in abilities:
        ct = (getattr(a, "cost_text", "") or "").lower()
        desc = (getattr(a, "description", "") or "").lower()
        if expected_cost in ct and expected_subtype.lower() in desc:
            return a
    return None


def _assert_typecycling(card_def, expected_subtype: str):
    """Wire the card in HAND and assert cycling ability registered."""
    assert getattr(card_def, "setup_in_hand", None) is not None, (
        f"{card_def.name} should have setup_in_hand for cycling"
    )
    game, p1, _ = _new_game()
    obj = _put_in_hand(game, p1, card_def)
    ability = _find_cycling_ability(obj, expected_subtype=expected_subtype)
    assert ability is not None, (
        f"{card_def.name} missing cycling activated ability with "
        f"cost '{{2}}, Discard this card' and {expected_subtype} target; "
        f"got abilities: {obj.state.activated_abilities!r}"
    )
    # Cost-parser must have flagged Discard this card so the cost engine
    # knows to remove the source from hand at activation time.
    assert getattr(ability, "discard_self", False), (
        f"{card_def.name} cycling ability should have discard_self=True"
    )
    # Mana portion should be {2} -> generic=2, no colored requirements.
    mc = getattr(ability, "mana_cost", None)
    if mc is not None:
        assert mc.generic == 2, (
            f"{card_def.name} cycling mana cost generic should be 2; got {mc.generic}"
        )


# =============================================================================
# DSK — Shepherding Spirits (Plainscycling {2})
# =============================================================================

def test_shepherding_spirits_plainscycling_registered():
    """Shepherding Spirits — Flying + Plainscycling {2}.

    The activated ability is registered on setup_in_hand via
    ``make_cycling_setup('{2}', typecycling='Plains')``.
    """
    print("\n=== shepherding_spirits: Plainscycling {2} ===")
    from src.cards.duskmourn import SHEPHERDING_SPIRITS
    _assert_typecycling(SHEPHERDING_SPIRITS, "Plains")
    print("  PASS")


# =============================================================================
# DSK — Daggermaw Megalodon (Islandcycling {2})
# =============================================================================

def test_daggermaw_megalodon_islandcycling_registered():
    """Daggermaw Megalodon — Vigilance + Islandcycling {2}."""
    print("\n=== daggermaw_megalodon: Islandcycling {2} ===")
    from src.cards.duskmourn import DAGGERMAW_MEGALODON
    _assert_typecycling(DAGGERMAW_MEGALODON, "Island")
    print("  PASS")


# =============================================================================
# DSK — Bedhead Beastie (Mountaincycling {2})
# =============================================================================

def test_bedhead_beastie_mountaincycling_registered():
    """Bedhead Beastie — Menace + Mountaincycling {2}."""
    print("\n=== bedhead_beastie: Mountaincycling {2} ===")
    from src.cards.duskmourn import BEDHEAD_BEASTIE
    _assert_typecycling(BEDHEAD_BEASTIE, "Mountain")
    print("  PASS")


# =============================================================================
# DSK — Slavering Branchsnapper (Forestcycling {2})
# =============================================================================

def test_slavering_branchsnapper_forestcycling_registered():
    """Slavering Branchsnapper — Trample + Forestcycling {2}."""
    print("\n=== slavering_branchsnapper: Forestcycling {2} ===")
    from src.cards.duskmourn import SLAVERING_BRANCHSNAPPER
    _assert_typecycling(SLAVERING_BRANCHSNAPPER, "Forest")
    print("  PASS")


# =============================================================================
# TLA — Saber-Tooth Moose-Lion (Forestcycling {2})
# =============================================================================

def test_sabertooth_mooselion_forestcycling_registered():
    """Saber-Tooth Moose-Lion — Reach + Forestcycling {2}."""
    print("\n=== sabertooth_mooselion: Forestcycling {2} ===")
    from src.cards.avatar_tla import SABERTOOTH_MOOSELION
    _assert_typecycling(SABERTOOTH_MOOSELION, "Forest")
    print("  PASS")


if __name__ == "__main__":
    test_shepherding_spirits_plainscycling_registered()
    test_daggermaw_megalodon_islandcycling_registered()
    test_bedhead_beastie_mountaincycling_registered()
    test_slavering_branchsnapper_forestcycling_registered()
    test_sabertooth_mooselion_forestcycling_registered()
    print("\nAll typecycling tests passed.")
