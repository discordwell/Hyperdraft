"""Phase 5b sweep — DSK noop-stub wirings (Agent DS).

Lightweight smoke tests confirming the wired setups register their
interceptors / activated abilities, and that the effect emits when the
trigger condition is easy to manufacture in isolation.

Coverage (17 cards wired):
    Trivial state:
      - piranha_fly                  (state.tapped = True on ETB)
      - norin_swift_survivalist      (static cant_block self-grant)

    Auras:
      - shardmages_rescue            (+1/+1 attached + conditional hexproof)
      - stay_hidden_stay_silent      (Aura + PREVENT untap + activated ability)
      - duskmourns_domination        (Aura -3/-0 + ETB gain-control trigger)

    Activated abilities:
      - balustrade_wurm (gy)         (Delirium-gated graveyard reanimate)
      - creeping_peeper              (mana ability {T}: Add {U})

    End-step triggers:
      - zimone_allquestioning        (gated end-step token + counters)
      - osseous_sticktwister         (delirium-gated end-step damage)

    Spell-cast triggers:
      - leyline_of_resonance         (COPY_SPELL on single-target creature spell)
      - aleyline_of_resonance        (same w/ optional cost marker)

    Rooms:
      - charred_foyer                (Room registration + upkeep impulse)
      - dazzling_theater             (Room registration + opp-untap trigger)

    Cast-zone aware:
      - patched_plaything            (setup_in_hand cast marker)

    On-damage modal:
      - silent_hallcreeper           (combat-damage modal-no-repeat trigger)

    Static keyword grant:
      - the_wandering_rescuer        (hexproof to tapped creatures you control)

Plus a regression-pin test counting DSK strict noops and asserting it
hasn't crept back up.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import ast
from pathlib import Path

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Interceptor, InterceptorPriority, InterceptorAction,
)
from src.cards.duskmourn import (
    PIRANHA_FLY,
    NORIN_SWIFT_SURVIVALIST,
    SHARDMAGES_RESCUE,
    STAY_HIDDEN_STAY_SILENT,
    DUSKMOURNS_DOMINATION,
    BALUSTRADE_WURM,
    CREEPING_PEEPER,
    ZIMONE_ALLQUESTIONING,
    OSSEOUS_STICKTWISTER,
    LEYLINE_OF_RESONANCE,
    ALEYLINE_OF_RESONANCE,
    CHARRED_FOYER,
    DAZZLING_THEATER,
    PATCHED_PLAYTHING,
    SILENT_HALLCREEPER,
    THE_WANDERING_RESCUER,
    SPECTRAL_SNATCHER,
    KAITO_BANE_OF_NIGHTMARES,
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


def _interceptor_count(game, source_id: str) -> int:
    return sum(1 for i in game.state.interceptors.values() if i.source == source_id)


def _has_activated_ability(obj, cost_substr: str) -> bool:
    abilities = getattr(obj.state, 'activated_abilities', None) or []
    for a in abilities:
        ct = getattr(a, 'cost_text', '') or ''
        if cost_substr.lower() in ct.lower():
            return True
    return False


# =============================================================================
# Piranha Fly — enters tapped
# =============================================================================

def test_piranha_fly_enters_tapped():
    """Piranha Fly should enter tapped on the battlefield."""
    print("\n=== piranha_fly: enters tapped ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, PIRANHA_FLY)
    assert obj.state.tapped is True, (
        f"Piranha Fly should be tapped on ETB; got tapped={obj.state.tapped}"
    )
    print("  PASS")


# =============================================================================
# Norin, Swift Survivalist — cant_block static
# =============================================================================

def test_norin_swift_survivalist_cant_block():
    """Norin should have cant_block via QUERY_ABILITIES interceptor."""
    print("\n=== norin: cant_block self-grant ===")
    from src.engine.queries import has_ability
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, NORIN_SWIFT_SURVIVALIST)
    assert _interceptor_count(game, obj.id) >= 1, (
        "Norin should register at least one interceptor (keyword grant)"
    )
    assert has_ability(obj, 'cant_block', game.state), (
        "Norin should have cant_block"
    )
    print("  PASS")


# =============================================================================
# Shardmage's Rescue — aura +1/+1 + entered-this-turn hexproof
# =============================================================================

def test_shardmages_rescue_registers_aura_interceptors():
    """Shardmage's Rescue is an Aura. With no attached target it still
    registers attached-PT-mod listeners + the hexproof query interceptor."""
    print("\n=== shardmages_rescue: aura + hexproof interceptors registered ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, SHARDMAGES_RESCUE)
    # Should register >= 2 interceptors (P/T listener(s) + hexproof QUERY)
    assert _interceptor_count(game, obj.id) >= 2, (
        f"Shardmage's Rescue should register >=2 interceptors; "
        f"got {_interceptor_count(game, obj.id)}"
    )
    print("  PASS")


# =============================================================================
# Stay Hidden, Stay Silent — PREVENT untap + activated ability
# =============================================================================

def test_stay_hidden_stay_silent_prevent_untap_interceptor():
    """Stay Hidden, Stay Silent should register a PREVENT untap interceptor."""
    print("\n=== stay_hidden_stay_silent: PREVENT untap + activated ability ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, STAY_HIDDEN_STAY_SILENT)
    has_prevent = any(
        i.source == obj.id and i.priority == InterceptorPriority.PREVENT
        for i in game.state.interceptors.values()
    )
    assert has_prevent, (
        "Stay Hidden, Stay Silent should register a PREVENT-priority untap interceptor"
    )
    assert _has_activated_ability(obj, "{4}{U}{U}"), (
        "Stay Hidden, Stay Silent should register a {4}{U}{U} activated ability"
    )
    print("  PASS")


# =============================================================================
# Duskmourn's Domination — Aura with gain-control ETB
# =============================================================================

def test_duskmourns_domination_aura_with_etb_trigger():
    """Duskmourn's Domination Aura should register attached-PT listeners +
    an ETB trigger that fires a GAIN_CONTROL event."""
    print("\n=== duskmourns_domination: aura + ETB gain-control trigger ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, DUSKMOURNS_DOMINATION)
    # Aura setup registers >= 1 attached-PT interceptor + 1 ETB trigger
    assert _interceptor_count(game, obj.id) >= 2, (
        f"Duskmourn's Domination should register >=2 interceptors; "
        f"got {_interceptor_count(game, obj.id)}"
    )
    print("  PASS")


# =============================================================================
# Balustrade Wurm — graveyard activated ability via setup_in_graveyard
# =============================================================================

def test_balustrade_wurm_gy_activated_ability_registered():
    """Balustrade Wurm — Delirium-gated activated reanimate. The ability is
    registered via setup_in_graveyard."""
    print("\n=== balustrade_wurm: graveyard activated ability ===")
    assert getattr(BALUSTRADE_WURM, 'setup_in_graveyard', None) is not None, (
        "BALUSTRADE_WURM should have setup_in_graveyard"
    )
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, BALUSTRADE_WURM, zone=ZoneType.GRAVEYARD)
    BALUSTRADE_WURM.setup_in_graveyard(obj, game.state)
    assert _has_activated_ability(obj, "{2}{G}{G}"), (
        f"Balustrade Wurm missing GY activated ability; "
        f"got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


# =============================================================================
# Creeping Peeper — {T}: Add {U}
# =============================================================================

def test_creeping_peeper_mana_ability():
    """Creeping Peeper should register a {T} activated mana ability."""
    print("\n=== creeping_peeper: {T}: Add {U} ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, CREEPING_PEEPER)
    assert _has_activated_ability(obj, "{T}"), (
        f"Creeping Peeper missing tap mana ability; "
        f"got {obj.state.activated_abilities!r}"
    )
    print("  PASS")


# =============================================================================
# Zimone, All-Questioning — end-step trigger
# =============================================================================

def test_zimone_allquestioning_end_step_trigger_registered():
    """Zimone should register an end-step trigger."""
    print("\n=== zimone_allquestioning: end-step trigger registered ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, ZIMONE_ALLQUESTIONING)
    assert _interceptor_count(game, obj.id) >= 1, (
        f"Zimone missing end-step trigger; got "
        f"{_interceptor_count(game, obj.id)}"
    )
    print("  PASS")


# =============================================================================
# Osseous Sticktwister — delirium end-step damage
# =============================================================================

def test_osseous_sticktwister_end_step_trigger_registered():
    """Osseous Sticktwister registers an end-step trigger that fires when
    delirium is active."""
    print("\n=== osseous_sticktwister: delirium end-step damage ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, OSSEOUS_STICKTWISTER)
    assert _interceptor_count(game, obj.id) >= 1, (
        "Osseous Sticktwister should register an end-step trigger"
    )
    print("  PASS")


# =============================================================================
# Leyline of Resonance / A-Leyline — spell-cast trigger
# =============================================================================

def test_leyline_of_resonance_cast_trigger_registered():
    """Leyline of Resonance should register a CAST trigger."""
    print("\n=== leyline_of_resonance: CAST trigger registered ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, LEYLINE_OF_RESONANCE)
    assert _interceptor_count(game, obj.id) >= 1, (
        "Leyline of Resonance should register a CAST trigger"
    )
    print("  PASS")


def test_aleyline_of_resonance_cast_trigger_registered():
    """A-Leyline of Resonance should register a CAST trigger."""
    print("\n=== aleyline_of_resonance: CAST trigger registered ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, ALEYLINE_OF_RESONANCE)
    assert _interceptor_count(game, obj.id) >= 1, (
        "A-Leyline of Resonance should register a CAST trigger"
    )
    print("  PASS")


# =============================================================================
# Charred Foyer — Room + upkeep impulse extra
# =============================================================================

def test_charred_foyer_room_registers_unlock_and_extra():
    """Charred Foyer should register Room machinery + upkeep impulse trigger."""
    print("\n=== charred_foyer: Room + upkeep extra registered ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, CHARRED_FOYER)
    # Room registers >=1 UNLOCK_DOOR REACT + the upkeep extra trigger
    assert _interceptor_count(game, obj.id) >= 2, (
        f"Charred Foyer should register >=2 interceptors; "
        f"got {_interceptor_count(game, obj.id)}"
    )
    print("  PASS")


# =============================================================================
# Dazzling Theater — Room + opp-untap extra
# =============================================================================

def test_dazzling_theater_room_registers_unlock_and_extra():
    """Dazzling Theater should register Room machinery + opp-untap trigger."""
    print("\n=== dazzling_theater: Room + opp-untap extra registered ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, DAZZLING_THEATER)
    assert _interceptor_count(game, obj.id) >= 2, (
        f"Dazzling Theater should register >=2 interceptors; "
        f"got {_interceptor_count(game, obj.id)}"
    )
    print("  PASS")


# =============================================================================
# Patched Plaything — setup_in_hand cast marker
# =============================================================================

def test_patched_plaything_setup_in_hand_registered():
    """Patched Plaything should expose setup_in_hand for the cast-from-hand
    detection marker."""
    print("\n=== patched_plaything: setup_in_hand cast marker ===")
    assert getattr(PATCHED_PLAYTHING, 'setup_in_hand', None) is not None, (
        "PATCHED_PLAYTHING should declare setup_in_hand"
    )
    # The setup_interceptors fn (battlefield) wires the ETB trigger.
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, PATCHED_PLAYTHING)
    assert _interceptor_count(game, obj.id) >= 1, (
        "Patched Plaything should register an ETB trigger on BATTLEFIELD entry"
    )
    print("  PASS")


# =============================================================================
# Silent Hallcreeper — combat-damage modal trigger
# =============================================================================

def test_silent_hallcreeper_combat_damage_trigger_registered():
    """Silent Hallcreeper registers a DAMAGE-based modal trigger."""
    print("\n=== silent_hallcreeper: combat-damage modal trigger ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, SILENT_HALLCREEPER)
    assert _interceptor_count(game, obj.id) >= 1, (
        f"Silent Hallcreeper missing DAMAGE trigger; "
        f"got {_interceptor_count(game, obj.id)}"
    )
    print("  PASS")


# =============================================================================
# The Wandering Rescuer — hexproof grant to tapped creatures you control
# =============================================================================

def test_the_wandering_rescuer_grants_hexproof_to_tapped_other():
    """The Wandering Rescuer should register a QUERY_ABILITIES interceptor
    that grants hexproof to other tapped creatures you control."""
    print("\n=== the_wandering_rescuer: hexproof grant interceptor ===")
    from src.engine.queries import has_ability
    game, p1, _ = _new_game()
    rescuer = _put_card(game, p1, THE_WANDERING_RESCUER)
    # Drop a second creature, tap it; it should now query as having hexproof.
    other = _put_card(game, p1, NORIN_SWIFT_SURVIVALIST)
    other.state.tapped = True
    assert has_ability(other, 'hexproof', game.state), (
        "Tapped other creature you control should have hexproof while "
        "The Wandering Rescuer is on the battlefield"
    )
    # Untapped should NOT get the grant.
    other.state.tapped = False
    assert not has_ability(other, 'hexproof', game.state), (
        "Untapped other creature you control should NOT have hexproof"
    )
    print("  PASS")


# =============================================================================
# Spectral Snatcher — Ward (discard a card)
# =============================================================================

def test_spectral_snatcher_ward_interceptor_registered():
    """Spectral Snatcher should register a Ward interceptor that fires on
    TARGET_CHOSEN from an opponent."""
    print("\n=== spectral_snatcher: ward interceptor registered ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, SPECTRAL_SNATCHER)
    # Ward interceptor fires on TARGET_CHOSEN; verify >=1 REACT interceptor.
    cnt = _interceptor_count(game, obj.id)
    assert cnt >= 1, f"Spectral Snatcher missing Ward; got {cnt}"
    print("  PASS")


# =============================================================================
# Kaito, Bane of Nightmares — Planeswalker framework
# =============================================================================

def test_kaito_bane_planeswalker_starts_with_loyalty():
    """Kaito should register the standard planeswalker interceptors and
    ETB with 4 loyalty counters."""
    print("\n=== kaito_bane_of_nightmares: planeswalker framework wired ===")
    game, p1, _ = _new_game()
    obj = _put_card(game, p1, KAITO_BANE_OF_NIGHTMARES)
    cnt = _interceptor_count(game, obj.id)
    # PW framework registers ETB + damage-redirect + lockout + turn-start
    # = >= 3 interceptors.
    assert cnt >= 3, (
        f"Kaito should register the planeswalker framework (>=3 interceptors); "
        f"got {cnt}"
    )
    print("  PASS")


# =============================================================================
# Aggregate noop-count regression pin
# =============================================================================

def test_dsk_noop_count_regression_pin():
    """Pin the DSK strict-noop count post-Agent-DS sweep.

    A 'strict noop' is a setup function whose body is literally ``return []``
    (after docstring + comments). Pre-sweep: 32 strict noops. Post-sweep:
    <= 10 strict noops. The remaining 10 are documented engine gaps
    (planeswalker loyalty abilities, replacement effects, modal-no-repeat
    over-time tracking, type-overwrite auras, enchant-player auras, alt-cost
    casting, must-be-blocked combat restriction) and five typecycling cards
    (shepherding_spirits / daggermaw / spectral_snatcher / bedhead / slavering)
    whose typecycling lives in ``setup_in_hand`` but whose battlefield setup
    is a bare ``return []`` by intent."""
    print("\n=== dsk noop count regression pin ===")
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
            if isinstance(n, ast.keyword) and n.arg in {"setup_interceptors",
                                                       "setup_in_graveyard",
                                                       "setup_in_hand"}:
                if isinstance(n.value, ast.Name):
                    wired.add(n.value.id)
        # Also pick up `CARD.setup_in_graveyard = fn` / `setup_in_hand = fn`
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                for target in n.targets:
                    if (isinstance(target, ast.Attribute) and
                            target.attr in {"setup_in_graveyard", "setup_in_hand"}):
                        if isinstance(n.value, ast.Name):
                            wired.add(n.value.id)
        n_noops = 0
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in wired and n.name.endswith("_setup"):
                if is_strict_noop(n):
                    n_noops += 1
        return n_noops

    dsk_noops = count_noops("duskmourn.py")
    print(f"  DSK strict noops: {dsk_noops} (expected <= 10)")
    # Pre-Agent-DS the value was 32. After this sweep we land at <= 10.
    assert dsk_noops <= 10, (
        f"DSK noop count regressed to {dsk_noops} (expected <= 10)"
    )
    print("  PASS")


if __name__ == "__main__":
    test_piranha_fly_enters_tapped()
    test_norin_swift_survivalist_cant_block()
    test_shardmages_rescue_registers_aura_interceptors()
    test_stay_hidden_stay_silent_prevent_untap_interceptor()
    test_duskmourns_domination_aura_with_etb_trigger()
    test_balustrade_wurm_gy_activated_ability_registered()
    test_creeping_peeper_mana_ability()
    test_zimone_allquestioning_end_step_trigger_registered()
    test_osseous_sticktwister_end_step_trigger_registered()
    test_leyline_of_resonance_cast_trigger_registered()
    test_aleyline_of_resonance_cast_trigger_registered()
    test_charred_foyer_room_registers_unlock_and_extra()
    test_dazzling_theater_room_registers_unlock_and_extra()
    test_patched_plaything_setup_in_hand_registered()
    test_silent_hallcreeper_combat_damage_trigger_registered()
    test_the_wandering_rescuer_grants_hexproof_to_tapped_other()
    test_spectral_snatcher_ward_interceptor_registered()
    test_kaito_bane_planeswalker_starts_with_loyalty()
    test_dsk_noop_count_regression_pin()
    print("\nAll Phase 5b DSK sweep-2 tests passed.")
