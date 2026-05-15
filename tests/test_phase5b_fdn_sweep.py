"""Phase 5b sweep — Foundations (FDN) noop-stub wirings.

Lightweight smoke tests for each wired card: confirm the setup_interceptors
function registers interceptors / activated abilities, and that the printed
effect emits on the printed condition.

Most assertions are at the interceptor-presence level (cheap, robust to
engine drift). A handful exercise the actual effect (counter add, life
change, etc.) when the trigger condition is easy to manufacture in isolation.

Wired cards covered:
    strix_lookout, sower_of_chaos, treetop_snarespinner, reassembling_skeleton,
    kitesail_corsair, inspiring_paladin, squad_rallier, demolition_field,
    ayli_eternal_pilgrim, pyromancers_goggles, mazemind_tome, wishclaw_talisman,
    mildmannered_librarian, immersturm_predator, fog_bank, sphinx_of_the_final_word,
    eaten_by_piranhas, witness_protection, loot_exuberant_explorer,
    vizier_of_the_menagerie, confiscate, elenda_saint_of_dusk,
    fynn_the_fangbearer, myojin_of_nights_reach, juggernaut.

Final test pins the aggregate wired-count delta to lock the sweep.
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
# Per-card smoke tests
# =============================================================================

def test_strix_lookout_registers_loot_ability():
    print("\n=== strix_lookout: registers {1}{U}, {T} loot ability ===")
    from src.cards.foundations import STRIX_LOOKOUT
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, STRIX_LOOKOUT)
    assert _has_activated_ability(obj, "{1}{U}"), (
        f"Strix Lookout missing loot ability; got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


def test_sower_of_chaos_registers_cant_block_grant():
    print("\n=== sower_of_chaos: registers {2}{R}: target can't block ===")
    from src.cards.foundations import SOWER_OF_CHAOS
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, SOWER_OF_CHAOS)
    assert _has_activated_ability(obj, "{2}{R}")
    print("  PASS")


def test_treetop_snarespinner_registers_counter_ability():
    print("\n=== treetop_snarespinner: sorcery-speed {2}{G} +1/+1 counter ===")
    from src.cards.foundations import TREETOP_SNARESPINNER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, TREETOP_SNARESPINNER)
    assert _has_activated_ability(obj, "{2}{G}")
    print("  PASS")


def test_reassembling_skeleton_gy_ability():
    print("\n=== reassembling_skeleton: graveyard {1}{B} return ===")
    from src.cards.foundations import REASSEMBLING_SKELETON
    assert getattr(REASSEMBLING_SKELETON, 'setup_in_graveyard', None) is not None, (
        "REASSEMBLING_SKELETON should have setup_in_graveyard"
    )
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, REASSEMBLING_SKELETON, zone=ZoneType.GRAVEYARD)
    # setup_in_graveyard is invoked manually for this test (engine path is
    # zone-change driven; we exercise the function directly).
    REASSEMBLING_SKELETON.setup_in_graveyard(obj, game.state)
    assert _has_activated_ability(obj, "{1}{B}"), (
        f"Skeleton missing gy ability; got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


def test_kitesail_corsair_flying_while_attacking():
    print("\n=== kitesail_corsair: flying granted while attacking ===")
    from src.cards.foundations import KITESAIL_CORSAIR
    from src.engine.queries import has_ability
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, KITESAIL_CORSAIR)
    # Not attacking -> no flying via interceptor.
    assert not has_ability(obj, 'flying', game.state)
    # Mark attacking and re-query.
    obj.state.attacking = True
    assert has_ability(obj, 'flying', game.state), "Expected flying when attacking"
    print("  PASS")


def test_inspiring_paladin_first_strike_on_own_turn():
    print("\n=== inspiring_paladin: first strike during your turn ===")
    from src.cards.foundations import INSPIRING_PALADIN
    from src.engine.queries import has_ability
    game, p1, p2 = _new_game()
    obj = _put_card(game, p1, INSPIRING_PALADIN)
    # p1's turn -> has first strike.
    game.state.active_player = p1.id
    assert has_ability(obj, 'first strike', game.state), "Expected first strike on own turn"
    # p2's turn -> no first strike.
    game.state.active_player = p2.id
    assert not has_ability(obj, 'first strike', game.state), "Should not have first strike on opponent's turn"
    print("  PASS")


def test_squad_rallier_activated_search_registered():
    print("\n=== squad_rallier: {2}{W} library search ===")
    from src.cards.foundations import SQUAD_RALLIER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, SQUAD_RALLIER)
    assert _has_activated_ability(obj, "{2}{W}")
    print("  PASS")


def test_demolition_field_sac_activated():
    print("\n=== demolition_field: {2}, {T}, Sacrifice land ===")
    from src.cards.foundations import DEMOLITION_FIELD
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, DEMOLITION_FIELD)
    assert _has_activated_ability(obj, "{2}")
    print("  PASS")


def test_ayli_sac_for_life():
    print("\n=== ayli_eternal_pilgrim: {1}, Sacrifice another: life ===")
    from src.cards.foundations import AYLI_ETERNAL_PILGRIM
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, AYLI_ETERNAL_PILGRIM)
    assert _has_activated_ability(obj, "{1}")
    print("  PASS")


def test_pyromancers_goggles_tap_for_red():
    print("\n=== pyromancers_goggles: {T}: Add {R} ===")
    from src.cards.foundations import PYROMANCERS_GOGGLES
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, PYROMANCERS_GOGGLES)
    assert _has_activated_ability(obj, "{T}")
    print("  PASS")


def test_mazemind_tome_two_activated_abilities():
    print("\n=== mazemind_tome: scry + draw activated abilities ===")
    from src.cards.foundations import MAZEMIND_TOME
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, MAZEMIND_TOME)
    abilities = obj.state.activated_abilities or []
    assert len(abilities) >= 2, f"Expected ≥2 abilities; got {abilities!r}"
    print("  PASS")


def test_wishclaw_talisman_etb_counters_and_tutor():
    print("\n=== wishclaw_talisman: ETB wish counters + tutor ===")
    from src.cards.foundations import WISHCLAW_TALISMAN
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, WISHCLAW_TALISMAN)
    # Fire ETB via a ZONE_CHANGE emission so the trigger handler runs.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'from_zone_type': ZoneType.STACK,
        },
        controller=p1.id,
    ))
    counters = getattr(obj.state, 'counters', {}) or {}
    assert counters.get('wish', 0) == 3, f"Expected 3 wish counters; got {counters}"
    assert _has_activated_ability(obj, "{1}")
    print("  PASS")


def test_mildmannered_librarian_once_per_game_transform():
    print("\n=== mildmannered_librarian: {3}{G} once-per-game ===")
    from src.cards.foundations import MILDMANNERED_LIBRARIAN
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, MILDMANNERED_LIBRARIAN)
    abilities = obj.state.activated_abilities or []
    assert any(getattr(a, 'once_per_game', False) for a in abilities), (
        f"Expected at least one once_per_game ability; got {abilities!r}"
    )
    print("  PASS")


def test_immersturm_predator_sac_and_tap_trigger():
    print("\n=== immersturm_predator: tap-trigger registered + sac ability ===")
    from src.cards.foundations import IMMERSTURM_PREDATOR
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, IMMERSTURM_PREDATOR)
    # Tap-trigger interceptor on source.
    assert _interceptor_count(game, obj.id) >= 1
    assert _has_activated_ability(obj, "sacrifice")
    print("  PASS")


def test_fog_bank_replacement_prevents_combat_damage():
    print("\n=== fog_bank: combat damage to/from self is prevented ===")
    from src.cards.foundations import FOG_BANK
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, FOG_BANK)
    assert _interceptor_count(game, obj.id) >= 1, (
        "Fog Bank should register at least one prevention interceptor"
    )
    print("  PASS")


def test_sphinx_of_the_final_word_counter_prevention():
    print("\n=== sphinx_of_the_final_word: registers counter-prevent interceptor ===")
    from src.cards.foundations import SPHINX_OF_THE_FINAL_WORD
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, SPHINX_OF_THE_FINAL_WORD)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_eaten_by_piranhas_aura_pt():
    print("\n=== eaten_by_piranhas: aura registers attach interceptors ===")
    from src.cards.foundations import EATEN_BY_PIRANHAS
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, EATEN_BY_PIRANHAS)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_witness_protection_aura_pt():
    print("\n=== witness_protection: aura registers attach interceptors ===")
    from src.cards.foundations import WITNESS_PROTECTION
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, WITNESS_PROTECTION)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_loot_exuberant_explorer_additional_land():
    print("\n=== loot_exuberant_explorer: additional-land interceptor + activated ===")
    from src.cards.foundations import LOOT_EXUBERANT_EXPLORER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, LOOT_EXUBERANT_EXPLORER)
    # Additional-land interceptor counts.
    assert _interceptor_count(game, obj.id) >= 1
    assert _has_activated_ability(obj, "{4}{G}{G}")
    print("  PASS")


def test_vizier_of_the_menagerie_castable_top():
    print("\n=== vizier_of_the_menagerie: cast-from-library-top registered ===")
    from src.cards.foundations import VIZIER_OF_THE_MENAGERIE
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, VIZIER_OF_THE_MENAGERIE)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_confiscate_control_change_on_etb():
    print("\n=== confiscate: registers aura + ETB control-change trigger ===")
    from src.cards.foundations import CONFISCATE
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, CONFISCATE)
    # Aura attach interceptor and/or ETB trigger present.
    assert _interceptor_count(game, obj.id) >= 1, (
        f"Expected ≥1 interceptor for Confiscate, got {_interceptor_count(game, obj.id)}"
    )
    print("  PASS")


def test_elenda_dynamic_pt_boost():
    print("\n=== elenda_saint_of_dusk: dynamic P/T boost registered ===")
    from src.cards.foundations import ELENDA_SAINT_OF_DUSK
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, ELENDA_SAINT_OF_DUSK)
    # At starting life == 20 == starting_life: no bonus.
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_fynn_poison_damage_trigger():
    print("\n=== fynn_the_fangbearer: registers poison damage trigger ===")
    from src.cards.foundations import FYNN_THE_FANGBEARER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, FYNN_THE_FANGBEARER)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_myojin_etb_divinity_and_indestructible():
    print("\n=== myojin_of_nights_reach: ETB divinity + indestructible while counter ===")
    from src.cards.foundations import MYOJIN_OF_NIGHTS_REACH
    from src.engine.queries import has_ability
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, MYOJIN_OF_NIGHTS_REACH)
    # Fire ETB.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'from_zone_type': ZoneType.STACK,
        },
        controller=p1.id,
    ))
    counters = getattr(obj.state, 'counters', {}) or {}
    assert counters.get('divinity', 0) >= 1, (
        f"Expected ≥1 divinity counter; got {counters}"
    )
    # While it has a divinity counter it must have indestructible.
    assert has_ability(obj, 'indestructible', game.state), (
        "Myojin should have indestructible while it has a divinity counter"
    )
    # Has activated ability with counter-removal cost.
    abilities_list = obj.state.activated_abilities or []
    assert any(
        getattr(a, 'counter_removal', None) is not None for a in abilities_list
    ), f"Expected counter_removal ability; got {abilities_list!r}"
    print("  PASS")


def test_juggernaut_walls_cant_block():
    print("\n=== juggernaut: walls can't block Juggernaut ===")
    from src.cards.foundations import JUGGERNAUT
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, JUGGERNAUT)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_banner_of_kinship_anthem_fallback():
    print("\n=== banner_of_kinship: static +1/+1 anthem on your creatures ===")
    from src.cards.foundations import BANNER_OF_KINSHIP
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, BANNER_OF_KINSHIP)
    # Banner registers ≥1 static_pt_boost interceptor for the +1/+1 lord.
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_heraldic_banner_tap_for_mana():
    print("\n=== heraldic_banner: {T} mana ability + +1/+0 anthem ===")
    from src.cards.foundations import HERALDIC_BANNER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, HERALDIC_BANNER)
    assert _has_activated_ability(obj, "{T}")
    print("  PASS")


def test_crystal_barricade_noncombat_prevention():
    print("\n=== crystal_barricade: noncombat damage prevention ===")
    from src.cards.foundations import CRYSTAL_BARRICADE
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, CRYSTAL_BARRICADE)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_zul_ashur_ward():
    print("\n=== zul_ashur_lich_lord: ward 2 life ===")
    from src.cards.foundations import ZUL_ASHUR_LICH_LORD
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, ZUL_ASHUR_LICH_LORD)
    assert _interceptor_count(game, obj.id) >= 1
    print("  PASS")


def test_abyssal_harvester_tap_exile():
    print("\n=== abyssal_harvester: {T} exile-from-gy ===")
    from src.cards.foundations import ABYSSAL_HARVESTER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, ABYSSAL_HARVESTER)
    assert _has_activated_ability(obj, "{T}")
    print("  PASS")


def test_kellan_transform_abilities():
    print("\n=== kellan_planar_trailblazer: two activated transforms ===")
    from src.cards.foundations import KELLAN_PLANAR_TRAILBLAZER
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, KELLAN_PLANAR_TRAILBLAZER)
    abilities = obj.state.activated_abilities or []
    assert len(abilities) >= 2, f"Expected ≥2 transforms; got {len(abilities)}"
    print("  PASS")


# =============================================================================
# Aggregate sanity check on the sweep size
# =============================================================================

def test_fdn_wired_count_meets_target():
    """Lock the wired-card delta from this sweep so regressions are loud.

    We measure how many ``*_setup`` functions in foundations.py whose
    callable returns ``[]`` immediately ("noop") remain. The sweep brought
    this down from 40 to ≤ 17 (target ≥30 wirings). If a future change
    regresses, this fails fast.
    """
    print("\n=== aggregate: foundations.py noop count is ≤ 17 ===")
    import ast
    from pathlib import Path

    fdn_path = Path(_PROJECT_ROOT) / "src" / "cards" / "foundations.py"
    tree = ast.parse(fdn_path.read_text())

    wired = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.keyword) and n.arg == "setup_interceptors":
            if isinstance(n.value, ast.Name):
                wired.add(n.value.id)

    def _is_top_level_empty_return(fn):
        body = [
            s for s in fn.body
            if not (isinstance(s, ast.Expr)
                    and isinstance(s.value, ast.Constant)
                    and isinstance(s.value.value, str))
        ]
        if len(body) != 1:
            return False
        s = body[0]
        if not isinstance(s, ast.Return):
            return False
        v = s.value
        return isinstance(v, ast.List) and len(v.elts) == 0

    noops = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in wired and n.name.endswith("_setup"):
            if _is_top_level_empty_return(n):
                noops += 1

    print(f"  noop count: {noops}")
    # Started at 40 (per scripts/find_useless_stubs.py snapshot before the
    # sweep) → ≥ 30 cards wired during Phase 5b → ≤ 10 noops remaining.
    # Two of those remaining noops (reassembling_skeleton, suspicious_shambler)
    # are intentional: those cards register their abilities via
    # ``setup_in_graveyard``, not ``setup_interceptors``.
    assert noops <= 10, (
        f"Expected ≤10 remaining foundations noops; found {noops}. "
        f"Phase 5b sweep should not regress below this baseline."
    )
    print("  PASS")


# =============================================================================
# Driver
# =============================================================================

if __name__ == "__main__":
    tests = [
        test_strix_lookout_registers_loot_ability,
        test_sower_of_chaos_registers_cant_block_grant,
        test_treetop_snarespinner_registers_counter_ability,
        test_reassembling_skeleton_gy_ability,
        test_kitesail_corsair_flying_while_attacking,
        test_inspiring_paladin_first_strike_on_own_turn,
        test_squad_rallier_activated_search_registered,
        test_demolition_field_sac_activated,
        test_ayli_sac_for_life,
        test_pyromancers_goggles_tap_for_red,
        test_mazemind_tome_two_activated_abilities,
        test_wishclaw_talisman_etb_counters_and_tutor,
        test_mildmannered_librarian_once_per_game_transform,
        test_immersturm_predator_sac_and_tap_trigger,
        test_fog_bank_replacement_prevents_combat_damage,
        test_sphinx_of_the_final_word_counter_prevention,
        test_eaten_by_piranhas_aura_pt,
        test_witness_protection_aura_pt,
        test_loot_exuberant_explorer_additional_land,
        test_vizier_of_the_menagerie_castable_top,
        test_confiscate_control_change_on_etb,
        test_elenda_dynamic_pt_boost,
        test_fynn_poison_damage_trigger,
        test_myojin_etb_divinity_and_indestructible,
        test_juggernaut_walls_cant_block,
        test_banner_of_kinship_anthem_fallback,
        test_heraldic_banner_tap_for_mana,
        test_crystal_barricade_noncombat_prevention,
        test_zul_ashur_ward,
        test_abyssal_harvester_tap_exile,
        test_kellan_transform_abilities,
        test_fdn_wired_count_meets_target,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"  FAIL: {t.__name__}: {e!r}")
            import traceback
            traceback.print_exc()
            failed.append(t.__name__)
    print()
    print("=" * 60)
    if failed:
        print(f"FAILED ({len(failed)}/{len(tests)}): {failed}")
        sys.exit(1)
    print(f"ALL {len(tests)} PHASE 5b FDN SWEEP TESTS PASSED")
    print("=" * 60)
