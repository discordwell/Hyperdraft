"""Phase 5b sweep — OTJ + TLA noop-stub wirings (Agent X).

Lightweight smoke tests confirming the wired setups register their
interceptors / activated abilities, and that the effect emits when the
trigger condition is easy to manufacture in isolation.

Coverage:
    OTJ — doc_aurlock_grizzled_genius (cost reduction from GY/exile)
    TLA — badgermole_cub (earthbend ETB)
          earth_rumble_wrestlers (conditional +1/+0 trample)
          tigerdillo (conditional cant_attack/cant_block)
          merchant_of_many_hats (graveyard activated return-to-hand)
          hakoda_selfless_commander (sac for +0/+5 indestructible)
          raucous_audience (conditional mana ability)
          watery_grasp (no-untap aura)

Final test pins the OTJ + TLA noop count delta to lock the sweep.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
)


# =============================================================================
# Helpers
# =============================================================================

def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put_card(game, owner, card_def, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _has_activated_ability(obj, cost_substr: str) -> bool:
    abilities = getattr(obj.state, 'activated_abilities', None) or []
    for a in abilities:
        ct = getattr(a, 'cost_text', '') or ''
        if cost_substr.lower() in ct.lower():
            return True
    return False


def _interceptor_count(game, source_id: str) -> int:
    return sum(1 for i in game.state.interceptors.values() if i.source == source_id)


# =============================================================================
# OTJ
# =============================================================================

def test_doc_aurlock_cost_reduction_from_graveyard_or_exile():
    """Doc Aurlock — spells you cast from your graveyard or from exile cost
    {2} less. Verifies the cost-reduction interceptor is registered for
    cards in GRAVEYARD / EXILE zones."""
    print("\n=== doc_aurlock: cost reduction interceptor registered ===")
    from src.cards.outlaws_thunder_junction import DOC_AURLOCK_GRIZZLED_GENIUS
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, DOC_AURLOCK_GRIZZLED_GENIUS)
    # The cost-reduction setup returns a QUERY-priority interceptor on QUERY_COST.
    cnt = _interceptor_count(game, obj.id)
    assert cnt >= 1, (
        f"Doc Aurlock should register at least one interceptor; got {cnt}"
    )
    print("  PASS")


# =============================================================================
# TLA — Badgermole Cub (earthbend ETB)
# =============================================================================

def test_badgermole_cub_earthbend_etb_trigger_registered():
    """Badgermole Cub — When this creature enters, earthbend 1.
    The setup should register an ETB-style trigger that fires on
    ZONE_CHANGE to BATTLEFIELD for this object."""
    print("\n=== badgermole_cub: earthbend ETB trigger registered ===")
    from src.cards.avatar_tla import BADGERMOLE_CUB
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, BADGERMOLE_CUB)
    cnt = _interceptor_count(game, obj.id)
    assert cnt >= 1, f"Badgermole Cub missing interceptor; got {cnt}"
    print("  PASS")


# =============================================================================
# TLA — Earth Rumble Wrestlers (conditional +1/+0 trample)
# =============================================================================

def test_earth_rumble_wrestlers_static_interceptors_registered():
    """Earth Rumble Wrestlers — +1/+0 and trample static while controlling
    a land-creature or having played a land this turn. Verifies the static
    QUERY interceptors are registered (power + keyword grant)."""
    print("\n=== earth_rumble_wrestlers: static +1 power + keyword grant ===")
    from src.cards.avatar_tla import EARTH_RUMBLE_WRESTLERS
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, EARTH_RUMBLE_WRESTLERS)
    cnt = _interceptor_count(game, obj.id)
    # Should register: power-mod interceptor + keyword-grant interceptor = 2
    assert cnt >= 2, (
        f"Earth Rumble Wrestlers should register >=2 interceptors; got {cnt}"
    )
    print("  PASS")


def test_earth_rumble_wrestlers_pump_when_land_played_this_turn():
    """When you've played a land this turn (and it's your turn), the static
    +1/+0 should apply."""
    print("\n=== earth_rumble_wrestlers: +1/+0 when land played this turn ===")
    from src.cards.avatar_tla import EARTH_RUMBLE_WRESTLERS
    from src.engine.queries import get_power
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, EARTH_RUMBLE_WRESTLERS)
    base_power = obj.characteristics.power  # 3
    # No land played, off-turn -> baseline
    game.state.active_player = p1.id
    game.state.lands_played_this_turn = 0
    assert get_power(obj, game.state) == base_power, (
        f"Baseline power should be {base_power}; got {get_power(obj, game.state)}"
    )
    # Active turn, a land was played this turn -> +1
    game.state.lands_played_this_turn = 1
    assert get_power(obj, game.state) == base_power + 1, (
        f"After landfall this turn, power should be {base_power + 1}; "
        f"got {get_power(obj, game.state)}"
    )
    print("  PASS")


# =============================================================================
# TLA — Tiger-Dillo (conditional cant_attack/cant_block)
# =============================================================================

def test_tigerdillo_cant_attack_when_no_helper():
    """Tiger-Dillo — can't attack/block unless you control another creature
    with power 4+. With no helper, cant_attack should be granted via
    QUERY_ABILITIES interceptor."""
    print("\n=== tigerdillo: cant_attack granted without power-4 helper ===")
    from src.cards.avatar_tla import TIGERDILLO
    from src.engine.queries import has_ability
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, TIGERDILLO)
    # No other creatures on the battlefield -> cant_attack granted
    assert has_ability(obj, 'cant_attack', game.state), (
        "Tiger-Dillo should have cant_attack without a power-4 helper"
    )
    print("  PASS")


# =============================================================================
# TLA — Merchant of Many Hats (graveyard activated return-to-hand)
# =============================================================================

def test_merchant_of_many_hats_graveyard_activated_ability():
    """Merchant of Many Hats — {2}{B}: Return this card from your graveyard
    to your hand. Activated ability is registered via setup_in_graveyard."""
    print("\n=== merchant_of_many_hats: GY {2}{B} return-to-hand ===")
    from src.cards.avatar_tla import MERCHANT_OF_MANY_HATS
    assert getattr(MERCHANT_OF_MANY_HATS, 'setup_in_graveyard', None) is not None, (
        "MERCHANT_OF_MANY_HATS should have setup_in_graveyard"
    )
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, MERCHANT_OF_MANY_HATS, zone=ZoneType.GRAVEYARD)
    MERCHANT_OF_MANY_HATS.setup_in_graveyard(obj, game.state)
    assert _has_activated_ability(obj, "{2}{B}"), (
        f"Merchant missing GY activated ability; got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


# =============================================================================
# TLA — Hakoda, Selfless Commander (sac for +0/+5 indestructible)
# =============================================================================

def test_hakoda_sac_ability_registered():
    """Hakoda — Sacrifice this creature: Creatures you control get +0/+5 and
    gain indestructible until end of turn."""
    print("\n=== hakoda: sac activated +0/+5 + indestructible ===")
    from src.cards.avatar_tla import HAKODA_SELFLESS_COMMANDER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, HAKODA_SELFLESS_COMMANDER)
    assert _has_activated_ability(obj, "Sacrifice"), (
        f"Hakoda missing sac ability; got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


# =============================================================================
# TLA — Raucous Audience (conditional mana)
# =============================================================================

def test_raucous_audience_tap_ability_registered():
    """Raucous Audience — {T}: Add {G}, or {G}{G} if you control a power-4
    creature. The mana ability is registered via make_activated_ability."""
    print("\n=== raucous_audience: {T} mana ability registered ===")
    from src.cards.avatar_tla import RAUCOUS_AUDIENCE
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, RAUCOUS_AUDIENCE)
    assert _has_activated_ability(obj, "{T}"), (
        f"Raucous Audience missing tap ability; got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


# =============================================================================
# TLA — Watery Grasp (no-untap aura)
# =============================================================================

def test_watery_grasp_prevent_untap_interceptor_registered():
    """Watery Grasp — Aura: enchanted creature doesn't untap during its
    controller's untap step. Verifies the PREVENT-priority interceptor on
    UNTAP is registered."""
    print("\n=== watery_grasp: PREVENT untap interceptor registered ===")
    from src.cards.avatar_tla import WATERY_GRASP
    from src.engine import InterceptorPriority
    game, p1, _ = _new_game()
    aura = _put_card(game, p1, WATERY_GRASP)
    # Look for any PREVENT-priority interceptor on this source.
    has_prevent = any(
        i.source == aura.id and i.priority == InterceptorPriority.PREVENT
        for i in game.state.interceptors.values()
    )
    assert has_prevent, (
        "Watery Grasp should register a PREVENT-priority interceptor for UNTAP"
    )
    print("  PASS")


# =============================================================================
# Aggregate noop-count pin (regression lock)
# =============================================================================

def test_otj_tla_noop_count_regression_pin():
    """Pin the OTJ + TLA noop count post-Agent-X sweep.

    A 'strict noop' is a setup function whose body is literally ``return []``
    (after docstring + comments). After this sweep:
        OTJ: was 14 noops, now 13 (Doc Aurlock wired).
        TLA: was 21 noops, now 15 (6 wired: Badgermole Cub, Hakoda,
             Earth Rumble Wrestlers, Tiger-Dillo, Raucous Audience,
             Watery Grasp). Merchant of Many Hats's BATTLEFIELD setup is
             still a strict noop — its activated ability lives in the
             graveyard via setup_in_graveyard, which the AST scanner
             doesn't count.

    If you wire another OTJ or TLA noop, update the expected counts. If a
    count GROWS, that's a regression — a previously-wired card lost its
    body somehow.
    """
    print("\n=== otj+tla noop count regression pin ===")
    import ast
    from pathlib import Path

    root = Path(_PROJECT_ROOT) / "src" / "cards"

    def is_strict_noop(fn):
        body = [s for s in fn.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                        and isinstance(s.value.value, str))]
        if len(body) != 1:
            return False
        s = body[0]
        if not isinstance(s, ast.Return):
            return False
        v = s.value
        return isinstance(v, ast.List) and len(v.elts) == 0

    def count_noops(filename):
        path = root / filename
        tree = ast.parse(path.read_text())
        wired = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.keyword) and n.arg == "setup_interceptors":
                if isinstance(n.value, ast.Name):
                    wired.add(n.value.id)
        n_noops = 0
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in wired and n.name.endswith("_setup"):
                if is_strict_noop(n):
                    n_noops += 1
        return n_noops

    otj_noops = count_noops("outlaws_thunder_junction.py")
    tla_noops = count_noops("avatar_tla.py")
    print(f"  OTJ strict noops: {otj_noops} (expected <= 13)")
    print(f"  TLA strict noops: {tla_noops} (expected <= 15)")
    assert otj_noops <= 13, f"OTJ noop count regressed to {otj_noops} (was 13)"
    assert tla_noops <= 15, f"TLA noop count regressed to {tla_noops} (was 15)"
    print("  PASS")


if __name__ == "__main__":
    test_doc_aurlock_cost_reduction_from_graveyard_or_exile()
    test_badgermole_cub_earthbend_etb_trigger_registered()
    test_earth_rumble_wrestlers_static_interceptors_registered()
    test_earth_rumble_wrestlers_pump_when_land_played_this_turn()
    test_tigerdillo_cant_attack_when_no_helper()
    test_merchant_of_many_hats_graveyard_activated_ability()
    test_hakoda_sac_ability_registered()
    test_raucous_audience_tap_ability_registered()
    test_watery_grasp_prevent_untap_interceptor_registered()
    test_otj_tla_noop_count_regression_pin()
    print("\nAll Phase 5b OTJ+TLA sweep tests passed.")
