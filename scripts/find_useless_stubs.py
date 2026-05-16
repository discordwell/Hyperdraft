"""Find setup_interceptors functions whose body is functionally a no-op.

A useless stub is one of:
  1. Body is literally `return []` with no triggers registered.
  2. Body returns a single helper-call but that helper's effect_fn returns
     []. (This DOES register a trigger though, so it's less useless — the
     engine fires the trigger but the effect is empty.)

We classify into:
  - 'noop'   : returns []  immediately. Trigger never fires. Equivalent to
               no setup_interceptors=.
  - 'trigger_empty' : registers a trigger (ETB / death / attack / etc.)
               whose inner effect_fn returns []. Useful as a hook for
               future engine work, but currently does nothing.
  - 'real'   : has at least one helper call AND emits at least one Event
               somewhere in the body. Also includes:
               * side-effect helpers (e.g. ``make_activated_ability(obj,...)
                 `` called for its side effect without returning the
                 result — common in WOE/MKM for activated abilities)
               * delegated setups (``return other_setup(obj, state)``) —
                 these reuse another wired setup wholesale.

This script's authority is bounded by the ``HELPER_NAMES`` allow-list. For
a *structural* check that is allow-list independent see
``scripts/strict_noop_audit.py`` — that script reports the smaller
"bare ``return []``" subset.
"""
from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS_DIR = ROOT / "src" / "cards"

SET_FILES = [
    "wilds_of_eldraine.py", "lost_caverns_ixalan.py", "murders_karlov_manor.py",
    "outlaws_thunder_junction.py", "bloomburrow.py", "duskmourn.py",
    "foundations.py", "edge_of_eternities.py", "lorwyn_eclipsed.py",
    "spider_man.py", "avatar_tla.py", "final_fantasy.py",
]

# Helper functions exported by src/cards/interceptor_helpers.py and
# src/engine/*.py whose call constitutes "registering at least one
# interceptor". Updated 2026-05-16 — keep in sync with grep:
#
#   grep -rn '^def make_\|^def register_\|^def becomes_\|^def threaten_\|^def grant_' \
#        src/cards/interceptor_helpers.py src/engine/
#
HELPER_NAMES: set[str] = {
    # --- Core triggers -------------------------------------------------
    "make_etb_trigger", "make_death_trigger", "make_attack_trigger",
    "make_block_trigger", "make_damage_trigger", "make_spell_cast_trigger",
    "make_tap_trigger", "make_upkeep_trigger", "make_end_step_trigger",
    "make_end_of_turn_trigger", "make_start_of_turn_trigger",
    "make_leaves_battlefield_trigger", "make_delayed_trigger",
    "make_life_gain_trigger", "make_life_loss_trigger", "make_draw_trigger",
    "make_counter_added_trigger", "make_enrage_trigger",
    "make_whenever_healed_trigger", "make_whenever_takes_damage_trigger",
    "make_life_gain_threshold_trigger", "make_nth_spell_cast_trigger",
    "make_morbid_etb_trigger", "make_attacks_alone_trigger",
    "make_counter_transfer_on_death",
    # --- Targeted (Phase 4+) -------------------------------------------
    "make_targeted_etb_trigger", "make_targeted_attack_trigger",
    "make_targeted_death_trigger", "make_targeted_damage_trigger",
    "make_targeted_spell_cast_trigger",
    "make_targeted_multi_effect_etb_trigger",
    "make_targeted_multi_effect_attack_trigger",
    # --- Static / P-T --------------------------------------------------
    "make_static_pt_boost", "make_dynamic_pt_boost",
    "make_attached_dynamic_pt_boost", "make_keyword_grant",
    "make_type_overwrite_aura",
    # --- Activated abilities (Phase 4) ---------------------------------
    "make_activated_ability", "make_exhaust_ability",
    "make_exhaust_reset_effect", "make_activate_exhaust_trigger",
    "make_pump_self_ability", "make_draw_ability", "make_loot_ability",
    "make_surveil_ability", "make_life_gain_ability", "make_damage_ability",
    "make_destroy_ability", "make_counter_ability",
    "make_token_creation_ability", "make_sac_destroy_ability",
    "make_granted_activated_ability", "make_activated_cost_reduction",
    # --- Cost / Ward / Mana --------------------------------------------
    "make_cost_reduction", "make_cost_reduction_aura", "make_ward",
    "make_shockland_setup", "make_lifeland_setup",
    "make_additional_land_play", "make_spell_damage_boost",
    "make_cant_attack", "make_cant_block",
    # --- Equipment / Aura attach (Phase 3) -----------------------------
    "make_equipment_setup", "make_aura_setup",
    # --- Set mechanics (Phase 5) ---------------------------------------
    "make_crime_trigger", "make_crime_committed_trigger",
    "make_saddle_trigger", "make_becomes_saddled_trigger",
    "set_saddle_threshold",
    "make_plot_setup", "make_becomes_plotted_trigger",
    "make_eerie_trigger", "make_survival_trigger", "make_impending_setup",
    "make_turned_face_up_trigger", "make_disguise_setup",
    "make_face_down_setup", "make_face_down_object", "make_manifest_etb_event",
    "make_offspring_setup", "make_forage_trigger", "make_expend_trigger",
    "make_valiant_trigger",
    "make_spree_setup", "make_spree_resolve",
    "make_room_setup", "make_saga_setup",
    "make_adventure_setup", "make_warp_setup",
    "make_web_slinging_setup", "make_mayhem_setup",
    "make_lander_etb_trigger", "make_lander_death_trigger",
    "make_lander_for_each_player_death_trigger",
    "make_void_end_step_trigger", "make_void_attack_trigger",
    "make_void_trigger", "make_station_creature_setup",
    "make_station_ability", "make_charge_threshold_ability",
    # --- Bend (TLA) ----------------------------------------------------
    "make_firebend_attack_trigger",
    "make_earthbend_etb_trigger", "make_earthbend_attack_trigger",
    "make_earthbend_death_trigger", "make_earthbend_spell_cast_trigger",
    "make_earthbend_end_step_trigger",
    "make_airbend_etb_trigger", "make_airbend_attack_trigger",
    "make_combined_bend_attack_trigger",
    # --- Replacement effects -------------------------------------------
    "make_replacement_effect", "make_replacement_interceptor",
    "make_life_gain_replacer", "make_life_gain_prevention",
    "make_draw_replacer", "make_dies_to_exile_replacer",
    "make_skip_to_graveyard_replacer", "make_graveyard_to_exile_replacer",
    "make_damage_doubler", "make_counter_doubler",
    # --- Cycling -------------------------------------------------------
    "make_cycling_setup", "make_cycling_ability",
    # --- Modal / Multi-effect / Misc -----------------------------------
    "make_modal_etb_trigger", "make_modal_spell_trigger",
    "make_modal_resolve", "make_divide_damage_resolve",
    "make_divided_damage_etb_trigger", "make_divided_counters_etb_trigger",
    "make_library_search_etb_trigger", "make_top_n_land_pick",
    "make_token_copy_from_graveyard", "make_copy_token_event",
    "make_copy_ability_event", "make_hand_to_battlefield_choice",
    "make_castable_from_zone", "make_castable_from_graveyard",
    "make_castable_from_exile", "make_castable_from_library_top",
    # --- Sweep / Grant helpers -----------------------------------------
    "becomes_creature", "becomes_copy_of", "threaten_creature",
    "grant_death_trigger", "grant_triggered_ability",
    "grant_activated_ability_on_attach", "grant_conspire",
    "make_granted_abilities_listener", "make_conspire_grant",
    # --- Planeswalker --------------------------------------------------
    "make_loyalty_ability", "make_planeswalker_setup",
    # --- Emblem / Animation / Vehicle ----------------------------------
    "make_emblem_setup", "make_emblem_creatures_have_keywords",
    "make_emblem_damage_target_react",
    "make_until_next_turn_animation", "make_animate_via_exhaust",
    "make_vehicle_animation_ability",
    # --- Tiered / Misc -------------------------------------------------
    "make_tiered_setup",
    # --- Register-style (no return needed) -----------------------------
    "register_ability_mirror", "register_activated_ability",
    "register_warp_end_step_exile",
}


def has_event_emitted(node: ast.AST) -> bool:
    """True if any sub-node creates an Event(...) call."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Event":
            return True
    return False


def has_interceptor_constructor(node: ast.AST) -> bool:
    """True if any sub-node creates an Interceptor(...) directly."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Interceptor":
            return True
    return False


def is_top_level_empty_return(fn: ast.FunctionDef) -> bool:
    """True if the function's only top-level statement is ``return []``
    (possibly preceded by a docstring).
    """
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    if len(body) != 1:
        return False
    s = body[0]
    if not isinstance(s, ast.Return):
        return False
    v = s.value
    return isinstance(v, ast.List) and len(v.elts) == 0


def is_delegated_setup(fn: ast.FunctionDef) -> bool:
    """True if body is ``return other_setup(obj, state)`` — reuses another
    wired setup by reference. These are *real* implementations, not noops.

    e.g. ``concealed_courtyard_setup`` -> ``blooming_marsh_setup``.
    """
    body = [s for s in fn.body
            if not (isinstance(s, ast.Expr)
                    and isinstance(s.value, ast.Constant)
                    and isinstance(s.value.value, str))]
    if len(body) != 1:
        return False
    s = body[0]
    if not isinstance(s, ast.Return):
        return False
    v = s.value
    if not isinstance(v, ast.Call):
        return False
    if not isinstance(v.func, ast.Name):
        return False
    return v.func.id.endswith("_setup") or v.func.id.endswith("_handler")


def helper_call_count(fn: ast.FunctionDef) -> int:
    return sum(
        1 for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in HELPER_NAMES
    )


def classify_setup(fn: ast.FunctionDef) -> str:
    """Return one of: 'real', 'trigger_empty', 'noop', 'delegated'.

    - delegated: body is `return other_setup(obj, state)` — by-reference reuse.
    - real: registers something AND emits at least one Event (or any
      helper call sequence that we're confident does something useful,
      such as ``make_activated_ability`` called for its side effect).
    - trigger_empty: registers a trigger/interceptor whose effect_fn body
      returns []; the trigger fires but the effect is empty.
    - noop: top-level body is literally ``return []`` AND no helper call
      anywhere inside (so the function is functionally identical to not
      passing setup_interceptors=).
    """
    if is_delegated_setup(fn):
        return "delegated"

    helpers = helper_call_count(fn)
    direct_interceptor = has_interceptor_constructor(fn)
    emits_event = has_event_emitted(fn)

    # Side-effect-only helper invocation (e.g. make_activated_ability
    # called without using its return value). Treat as real iff at least
    # one helper is called somewhere AND no top-level bare return [].
    side_effect_helper = helpers > 0 and not is_top_level_empty_return(fn)

    if is_top_level_empty_return(fn):
        # Even with a bare `return []`, if a helper was called inside the
        # function (e.g. `make_activated_ability(obj, ...)` for its side
        # effect, then `return []`), that's real registration.
        if helpers > 0:
            return "real"
        return "noop"
    if helpers == 0 and not direct_interceptor:
        # Function body has logic but never registers anything.
        return "noop"
    if emits_event or direct_interceptor or side_effect_helper:
        return "real"
    return "trigger_empty"


def main() -> None:
    by_set: dict[str, Counter] = {}
    noop_examples: dict[str, list[tuple[str, int]]] = defaultdict(list)
    grand = Counter()

    for fname in SET_FILES:
        path = CARDS_DIR / fname
        tree = ast.parse(path.read_text())

        # Build set of wired setup function names
        wired = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.keyword) and n.arg in {"setup_interceptors",
                                                         "setup_in_graveyard"}:
                if isinstance(n.value, ast.Name):
                    wired.add(n.value.id)

        counts = Counter()
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef) and n.name in wired:
                cls = classify_setup(n)
                counts[cls] += 1
                grand[cls] += 1
                if cls == "noop":
                    noop_examples[fname].append((n.name, n.lineno))
        by_set[fname] = counts

    cats = ["real", "delegated", "trigger_empty", "noop"]
    print(f"{'set':<32}" + "".join(f"{c[:10]:>11}" for c in cats) + f"{'total':>8}")
    print("-" * 80)
    for fname, counts in by_set.items():
        total = sum(counts.values())
        row = "".join(f"{counts.get(c, 0):>11}" for c in cats)
        print(f"{fname:<32}{row}{total:>8}")
    print("-" * 80)
    grand_total = sum(grand.values())
    print(f"{'TOTAL':<32}" + "".join(f"{grand[c]:>11}" for c in cats) + f"{grand_total:>8}")
    print()
    if grand_total:
        pct = 100 * grand['noop'] / grand_total
        print(f"Bare-return-[] 'noop' setups: {grand['noop']} ({pct:.1f}% of wired)")
        print(f"  These are functionally identical to NOT having setup_interceptors=.")
    print()
    print("Per-set noop examples:")
    for fname, exs in noop_examples.items():
        if not exs:
            continue
        print(f"  {fname}: {len(exs)} noops")
        for name, lineno in exs[:5]:
            print(f"    L{lineno:5d}  {name}")


if __name__ == "__main__":
    main()
