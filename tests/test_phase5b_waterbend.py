"""Phase 5b sweep — TLA Waterbend activated-ability framework (Agent Y).

Verifies the ``make_waterbend_activated_ability`` helper plumbs the
printed waterbend cost as a real activated ability, and that each wired
TLA card registers a descriptor with the correct cost.

For cards whose effect is easy to manufacture in isolation we also run
the effect_fn directly and assert the expected events fire — including
the trailing ``BENDING_WATERBEND`` marker that every waterbend
activation appends so trackers (e.g. Avatar Aang) observe the action.

Coverage:
    Water Tribe Rallier       ({5}: top-4 power<=3 tutor)
    Flexible Waterbender      ({3}: base 5/2 EOT)
    Geyser Leaper             ({4}: loot)
    Giant Koi                 ({3}: unblockable this turn)
    Katara, Bending Prodigy   ({6}: draw a card)
    North Pole Patrol         ({3}, {T}: tap target opp creature)
    The Unagi of Kyoshi Island (ward {4} + opp-2nd-draw react)
    Waterbender Ascension     ({4}: target unblockable EOT)
    Yue, the Moon Spirit      ({5}, {T}: cast free — engine-gap deferred)
    Foggy Swamp Vinebender    ({5}: +1/+1 counter, own_turn_only)
    Watery Grasp              ({5}: shuffle enchanted)

Final test pins the TLA waterbend-gap count: how many cards still carry
an "engine gap: waterbend" comment with no registered waterbend cost
descriptor on their setup output.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
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


def _find_ability(obj, cost_substr: str):
    """Return the first activated ability whose cost_text contains the
    substring (case-insensitive)."""
    for ability in (obj.state.activated_abilities or []):
        ct = (ability.cost_text or "").lower()
        if cost_substr.lower() in ct:
            return ability
    return None


def _has_ability_cost(obj, cost_substr: str) -> bool:
    return _find_ability(obj, cost_substr) is not None


def _bending_marker_events(events) -> list:
    """Filter to BENDING_WATERBEND marker events."""
    return [e for e in events if e.type == EventType.BENDING_WATERBEND]


# =============================================================================
# Framework smoke test
# =============================================================================

def test_make_waterbend_activated_ability_registers_cost_and_marker():
    """The helper should register a descriptor whose cost_text is the
    printed waterbend cost, and whose effect_fn appends a
    BENDING_WATERBEND marker after the user-supplied effects."""
    print("\n=== framework: make_waterbend_activated_ability ===")
    from src.engine.bending import make_waterbend_activated_ability
    from src.cards.avatar_tla import GEYSER_LEAPER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, GEYSER_LEAPER)
    ability = _find_ability(obj, "{4}")
    assert ability is not None, (
        f"Geyser Leaper should register a {{4}} ability; got "
        f"{obj.state.activated_abilities!r}"
    )
    # Run the effect through the wrapped fn — should emit DRAW, DISCARD_CHOICE,
    # then the marker.
    events = list(ability.effect_fn(obj, game.state, []) or [])
    types = [e.type for e in events]
    assert EventType.DRAW in types, f"missing DRAW; got {types}"
    assert EventType.DISCARD_CHOICE in types, f"missing DISCARD_CHOICE; got {types}"
    markers = _bending_marker_events(events)
    assert len(markers) == 1, (
        f"expected exactly one BENDING_WATERBEND marker; got {len(markers)}"
    )
    payload = markers[0].payload
    assert payload.get('amount') == 4, (
        f"marker amount should reflect printed cost 4; got {payload!r}"
    )
    assert payload.get('controller') == obj.controller
    print("  PASS")


# =============================================================================
# Per-card smoke tests
# =============================================================================

def test_water_tribe_rallier_waterbend_5_registered():
    print("\n=== water_tribe_rallier: waterbend {5} registered ===")
    from src.cards.avatar_tla import WATER_TRIBE_RALLIER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, WATER_TRIBE_RALLIER)
    assert _has_ability_cost(obj, "{5}"), (
        f"Water Tribe Rallier missing {{5}} ability; got "
        f"{obj.state.activated_abilities!r}"
    )
    ability = _find_ability(obj, "{5}")
    events = list(ability.effect_fn(obj, game.state, []) or [])
    types = [e.type for e in events]
    assert EventType.SEARCH_LIBRARY in types, (
        f"effect should emit SEARCH_LIBRARY; got {types}"
    )
    assert _bending_marker_events(events), "missing BENDING_WATERBEND marker"
    print("  PASS")


def test_flexible_waterbender_waterbend_3_registered():
    print("\n=== flexible_waterbender: waterbend {3} registered ===")
    from src.cards.avatar_tla import FLEXIBLE_WATERBENDER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, FLEXIBLE_WATERBENDER)
    assert _has_ability_cost(obj, "{3}"), (
        f"Flexible Waterbender missing {{3}} ability"
    )
    ability = _find_ability(obj, "{3}")
    events = list(ability.effect_fn(obj, game.state, []) or [])
    pt_events = [e for e in events if e.type == EventType.PT_MODIFICATION]
    assert len(pt_events) == 1, (
        f"expected one PT_MODIFICATION event; got {[e.type for e in events]}"
    )
    pl = pt_events[0].payload
    # base 2/5 -> 5/2 means +3 power, -3 toughness
    assert pl.get('power_mod') == 3 and pl.get('toughness_mod') == -3, (
        f"expected +3/-3 PT delta; got {pl!r}"
    )
    assert pl.get('duration') == 'end_of_turn'
    assert _bending_marker_events(events)
    print("  PASS")


def test_geyser_leaper_waterbend_4_registered():
    print("\n=== geyser_leaper: waterbend {4} registered ===")
    from src.cards.avatar_tla import GEYSER_LEAPER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, GEYSER_LEAPER)
    assert _has_ability_cost(obj, "{4}")
    print("  PASS")


def test_giant_koi_waterbend_3_registered():
    print("\n=== giant_koi: waterbend {3} registered ===")
    from src.cards.avatar_tla import GIANT_KOI
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, GIANT_KOI)
    assert _has_ability_cost(obj, "{3}"), (
        f"Giant Koi missing {{3}} ability"
    )
    ability = _find_ability(obj, "{3}")
    events = list(ability.effect_fn(obj, game.state, []) or [])
    types = [e.type for e in events]
    assert EventType.GRANT_UNBLOCKABLE in types, (
        f"effect should emit GRANT_UNBLOCKABLE; got {types}"
    )
    print("  PASS")


def test_katara_bending_prodigy_waterbend_6_registered():
    print("\n=== katara_bending_prodigy: waterbend {6} + end step ===")
    from src.cards.avatar_tla import KATARA_BENDING_PRODIGY
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, KATARA_BENDING_PRODIGY)
    assert _has_ability_cost(obj, "{6}"), "Katara missing {6} waterbend draw"
    ability = _find_ability(obj, "{6}")
    events = list(ability.effect_fn(obj, game.state, []) or [])
    types = [e.type for e in events]
    assert EventType.DRAW in types, f"missing DRAW; got {types}"
    # End-step trigger should also still be there
    end_step_ic = [
        i for i in game.state.interceptors.values() if i.source == obj.id
    ]
    assert len(end_step_ic) >= 1, "Katara should retain end-step trigger"
    print("  PASS")


def test_north_pole_patrol_two_activations_registered():
    print("\n=== north_pole_patrol: {T} untap + waterbend {3},{T} tap ===")
    from src.cards.avatar_tla import NORTH_POLE_PATROL
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, NORTH_POLE_PATROL)
    # Should have TWO activated abilities now: the {T} untap and the
    # waterbend {3},{T} tap-opp.
    costs = [a.cost_text for a in (obj.state.activated_abilities or [])]
    assert any('{T}' in c and '{3}' not in c for c in costs), (
        f"missing the {{T}} untap ability; costs={costs!r}"
    )
    assert any('{3}' in c and '{T}' in c for c in costs), (
        f"missing the waterbend {{3}}, {{T}} tap ability; costs={costs!r}"
    )
    print("  PASS")


def test_the_unagi_ward_4_and_second_draw_react():
    print("\n=== the_unagi_of_kyoshi_island: ward + 2nd-draw trigger ===")
    from src.cards.avatar_tla import THE_UNAGI_OF_KYOSHI_ISLAND
    from src.engine import InterceptorPriority
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, THE_UNAGI_OF_KYOSHI_ISLAND)
    # Two interceptors should be registered: ward + opp-2nd-draw react.
    ics = [i for i in game.state.interceptors.values() if i.source == obj.id]
    assert len(ics) >= 2, (
        f"The Unagi should register >=2 interceptors; got {len(ics)}"
    )
    # At least one REACT-priority interceptor (the 2nd-draw trigger).
    react_ics = [i for i in ics if i.priority == InterceptorPriority.REACT]
    assert react_ics, "should register a REACT-priority second-draw trigger"
    print("  PASS")


def test_waterbender_ascension_waterbend_4_registered():
    print("\n=== waterbender_ascension: waterbend {4} unblockable ===")
    from src.cards.avatar_tla import WATERBENDER_ASCENSION
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, WATERBENDER_ASCENSION)
    assert _has_ability_cost(obj, "{4}"), (
        f"Waterbender Ascension missing {{4}} waterbend ability; got "
        f"{obj.state.activated_abilities!r}"
    )
    ability = _find_ability(obj, "{4}")
    assert ability.targets_required == 1
    print("  PASS")


def test_yue_the_moon_spirit_waterbend_registered():
    print("\n=== yue_the_moon_spirit: waterbend {5},{T} registered ===")
    from src.cards.avatar_tla import YUE_THE_MOON_SPIRIT
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, YUE_THE_MOON_SPIRIT)
    assert _has_ability_cost(obj, "{5}"), (
        f"Yue missing {{5}}, {{T}} ability; got "
        f"{obj.state.activated_abilities!r}"
    )
    print("  PASS")


def test_foggy_swamp_vinebender_waterbend_5_own_turn_only():
    print("\n=== foggy_swamp_vinebender: waterbend {5} own-turn-only ===")
    from src.cards.avatar_tla import FOGGY_SWAMP_VINEBENDER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, FOGGY_SWAMP_VINEBENDER)
    ability = _find_ability(obj, "{5}")
    assert ability is not None, (
        f"Foggy Swamp Vinebender missing {{5}} ability"
    )
    assert ability.own_turn_only is True, (
        f"Vinebender waterbend should be own_turn_only; got "
        f"own_turn_only={ability.own_turn_only}, sorcery_speed="
        f"{ability.sorcery_speed}"
    )
    events = list(ability.effect_fn(obj, game.state, []) or [])
    types = [e.type for e in events]
    assert EventType.COUNTER_ADDED in types, (
        f"effect should emit COUNTER_ADDED; got {types}"
    )
    print("  PASS")


def test_watery_grasp_waterbend_5_shuffle_registered():
    print("\n=== watery_grasp: waterbend {5} shuffle enchanted ===")
    from src.cards.avatar_tla import WATERY_GRASP
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, WATERY_GRASP)
    assert _has_ability_cost(obj, "{5}"), (
        f"Watery Grasp missing {{5}} waterbend ability; got "
        f"{obj.state.activated_abilities!r}"
    )
    print("  PASS")


# =============================================================================
# Regression-pin: how many TLA setups still carry a strict-noop waterbend gap
# =============================================================================

def test_tla_waterbend_gap_regression_pin():
    """Count TLA ``*_setup`` functions whose body is literally ``return []``
    AND whose docstring/comments mention 'waterbend'. After Agent Y's
    sweep this should be 0 (all known stubs are wired).

    If a NEW waterbend stub appears, it'll fail this pin until you wire
    it (or update the expected count).
    """
    print("\n=== tla waterbend gap regression pin ===")
    import ast
    from pathlib import Path

    root = Path(_PROJECT_ROOT) / "src" / "cards"
    path = root / "avatar_tla.py"
    tree = ast.parse(path.read_text())

    wired = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.keyword) and n.arg == "setup_interceptors":
            if isinstance(n.value, ast.Name):
                wired.add(n.value.id)

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

    def mentions_waterbend(fn) -> bool:
        # Scan docstring + inline comments.
        if fn.body and isinstance(fn.body[0], ast.Expr) and \
                isinstance(fn.body[0].value, ast.Constant) and \
                isinstance(fn.body[0].value.value, str):
            doc = fn.body[0].value.value.lower()
            if 'waterbend' in doc:
                return True
        # Heuristic — scan source segment for 'waterbend' in any comment line
        # within the function body's textual span.
        src = ast.get_source_segment(path.read_text(), fn) or ""
        return 'waterbend' in src.lower()

    noops_with_waterbend = []
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in wired and n.name.endswith("_setup"):
            if is_strict_noop(n) and mentions_waterbend(n):
                noops_with_waterbend.append(n.name)

    print(f"  TLA strict-noop setups mentioning waterbend: {len(noops_with_waterbend)}")
    for name in noops_with_waterbend:
        print(f"    - {name}")
    # After Agent Y: zero waterbend stubs should remain as strict noops.
    # If you wire a new card whose setup turns into a non-noop, this stays at 0.
    assert len(noops_with_waterbend) <= 0, (
        f"TLA waterbend-gap regression: {len(noops_with_waterbend)} strict-noop "
        f"setups still mention waterbend ({noops_with_waterbend!r}). Wire them "
        f"or update this pin."
    )
    print("  PASS")


if __name__ == "__main__":
    test_make_waterbend_activated_ability_registers_cost_and_marker()
    test_water_tribe_rallier_waterbend_5_registered()
    test_flexible_waterbender_waterbend_3_registered()
    test_geyser_leaper_waterbend_4_registered()
    test_giant_koi_waterbend_3_registered()
    test_katara_bending_prodigy_waterbend_6_registered()
    test_north_pole_patrol_two_activations_registered()
    test_the_unagi_ward_4_and_second_draw_react()
    test_waterbender_ascension_waterbend_4_registered()
    test_yue_the_moon_spirit_waterbend_registered()
    test_foggy_swamp_vinebender_waterbend_5_own_turn_only()
    test_watery_grasp_waterbend_5_shuffle_registered()
    test_tla_waterbend_gap_regression_pin()
    print("\nAll Phase 5b TLA waterbend tests passed.")
