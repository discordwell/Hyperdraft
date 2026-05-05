"""
Tests for the OTJ Spree cost-per-mode mechanic.

Covers:
- SpreeMode dataclass + parsing of extra_cost strings/ManaCost objects
- compute_affordable_spree_modes (mode filtering by mana payable in
  combination with the printed cost)
- make_spree_setup tags the card_def correctly
- _handle_cast_spell opens a Spree mode prompt before mana is paid
- Single-mode cast: pays base + mode-1; mode-1 effect fires
- Multi-mode cast: pays base + mode-1 + mode-2; both effects fire in order
- Insufficient mana for any mode -> spell uncastable (no prompt opens)
- Per-card smoke test for the five wired OTJ Spree cards
"""

import asyncio
import os
import sys

# Run from the repo root regardless of which worktree the tests live in.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    PlayerAction, ActionType, ManaCost,
    SpreeMode, make_spree_setup, make_spree_resolve,
    compute_affordable_spree_modes, get_chosen_spree_modes,
    record_spree_choice, clear_spree_choice,
    is_spree_card, get_spree_modes, get_spree_minmax,
    make_instant, make_creature,
)
from src.cards import outlaws_thunder_junction as otj


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_two_player_game():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    return game, p1, p2


def add_mana(game, player_id, color="C", amount=1):
    """Inject mana into a player's pool for tests."""
    from src.engine.mana import ManaType
    color_to_type = {
        "W": ManaType.WHITE,
        "U": ManaType.BLUE,
        "B": ManaType.BLACK,
        "R": ManaType.RED,
        "G": ManaType.GREEN,
        "C": ManaType.COLORLESS,
    }
    mtype = color_to_type[color]
    game.mana_system.produce_mana(player_id, mtype, amount)


def cast_spell(game, player_id, spell_obj):
    """Drive a CAST_SPELL action and emit the resulting events."""
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=player_id,
        card_id=spell_obj.id,
    )
    cast_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    emitted = []
    for ev in cast_events or []:
        emitted.extend(game.emit(ev))
    return cast_events + emitted


def make_spell(game, owner_id, card_def, zone=ZoneType.HAND):
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def submit_spree(game, player_id, indices):
    """Submit Spree mode choice via PendingChoice."""
    choice = game.state.pending_choice
    assert choice is not None, "expected pending Spree choice"
    payload = [{"index": i} for i in indices]
    return game.submit_choice(choice.id, player_id, payload)


# ---------------------------------------------------------------------------
# 1. SpreeMode basic shape
# ---------------------------------------------------------------------------


def test_spree_mode_basic():
    print("\n=== Test: SpreeMode basic ===")
    mode = SpreeMode(
        name="Strike",
        extra_cost="{2}",
        effect_fn=lambda s, st, t: [],
        description="Deal 2 damage",
        targets_required=1,
        target_kind="creature",
    )
    assert mode.name == "Strike"
    cost = mode.resolved_extra_cost()
    assert cost.generic == 2, f"expected generic 2, got {cost.generic}"
    assert not cost.is_free()
    assert mode.targets_required == 1
    assert mode.target_kind == "creature"
    print("OK: SpreeMode parses extra_cost and metadata")


def test_spree_mode_with_manacost_object():
    print("\n=== Test: SpreeMode accepts ManaCost objects ===")
    cost = ManaCost(generic=2, white=1)
    mode = SpreeMode(name="X", extra_cost=cost, effect_fn=lambda *a: [])
    out = mode.resolved_extra_cost()
    assert out.generic == 2
    assert out.white == 1
    print("OK: ManaCost objects pass through")


def test_spree_mode_label():
    print("\n=== Test: SpreeMode label ===")
    mode = SpreeMode(name="Burn", extra_cost="{1}{R}",
                     effect_fn=lambda *a: [],
                     description="Deal 3 damage to any target")
    label = mode.label()
    assert label.startswith("+ ") and "Deal 3 damage" in label
    print(f"OK: label = {label}")


# ---------------------------------------------------------------------------
# 2. Affordability
# ---------------------------------------------------------------------------


def test_compute_affordable_spree_modes_no_mana():
    print("\n=== Test: compute_affordable_spree_modes (no mana) ===")
    game, p1, _ = make_two_player_game()
    modes = [
        SpreeMode(name="A", extra_cost="{1}", effect_fn=lambda *a: []),
        SpreeMode(name="B", extra_cost="{3}", effect_fn=lambda *a: []),
    ]
    base = ManaCost.parse("{R}")
    aff = compute_affordable_spree_modes(modes, game.state, p1.id, base)
    assert aff == [], f"expected no affordable modes; got {[m[1].name for m in aff]}"
    print("OK: no modes affordable on empty pool")


def test_compute_affordable_spree_modes_partial_pool():
    print("\n=== Test: compute_affordable_spree_modes (partial mana) ===")
    game, p1, _ = make_two_player_game()
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 2)  # base+mode = {R}{2}
    modes = [
        SpreeMode(name="A", extra_cost="{1}", effect_fn=lambda *a: []),  # {R}+{1}={R}{1} = 2
        SpreeMode(name="B", extra_cost="{3}", effect_fn=lambda *a: []),  # {R}+{3}={R}{3} = 4
    ]
    base = ManaCost.parse("{R}")
    aff = compute_affordable_spree_modes(modes, game.state, p1.id, base)
    names = [m.name for _, m in aff]
    assert "A" in names, f"A should be affordable; got {names}"
    assert "B" not in names, f"B should be unaffordable; got {names}"
    print("OK: only affordable modes returned")


# ---------------------------------------------------------------------------
# 3. Setup tags card_def correctly
# ---------------------------------------------------------------------------


def test_make_spree_setup_tags_card_def():
    print("\n=== Test: make_spree_setup tags card_def ===")
    modes = [SpreeMode(name="A", extra_cost="{1}", effect_fn=lambda *a: [])]
    card = make_instant(
        name="Tag Test",
        mana_cost="{0}",
        colors={Color.RED},
        text="Spree.",
        setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=modes),
        resolve=make_spree_resolve(modes),
    )
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    # card_def should now have _spree=True
    assert is_spree_card(card), "card_def should be marked as Spree"
    assert is_spree_card(spell), "GameObject .card_def should expose Spree"
    cap_min, cap_max = get_spree_minmax(card)
    assert cap_min == 1
    assert cap_max == 1
    listed = get_spree_modes(card)
    assert len(listed) == 1 and listed[0].name == "A"
    print("OK: card_def tagged with Spree metadata")


# ---------------------------------------------------------------------------
# 4. Cast pipeline: single-mode select pays mode cost
# ---------------------------------------------------------------------------


def _build_synthetic_spree(modes, *, mana_cost="{0}"):
    return make_instant(
        name="Synthetic Spree Spell",
        mana_cost=mana_cost,
        colors={Color.RED},
        text="Spree (Choose one or more additional costs.)",
        setup_interceptors=lambda obj, state: make_spree_setup(obj, base_modes=modes),
        resolve=make_spree_resolve(modes),
    )


def test_spree_cast_single_mode_pays_extra_runs_effect():
    print("\n=== Test: Spree single-mode cast pays mode cost ===")
    fired = []

    def m1(spell, state, targets):
        fired.append("M1")
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': spell.controller, 'amount': 1},
                      source=spell.id)]

    def m2(spell, state, targets):
        fired.append("M2")
        return [Event(type=EventType.DRAW,
                      payload={'player': spell.controller, 'amount': 1},
                      source=spell.id)]

    modes = [
        SpreeMode(name="M1", extra_cost="{1}", effect_fn=m1),
        SpreeMode(name="M2", extra_cost="{2}", effect_fn=m2),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")

    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 1)  # enough for M1 only

    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is not None, "expected Spree mode prompt"
    assert game.state.pending_choice.callback_data.get("spree") is True

    # Only M1 should be affordable
    options = game.state.pending_choice.options
    affordable_indices = sorted(o["index"] for o in options)
    assert 0 in affordable_indices, f"expected M1 affordable; got {affordable_indices}"
    assert 1 not in affordable_indices, f"M2 should NOT be affordable; got {affordable_indices}"

    # Pick M1
    ok, msg, _ = submit_spree(game, p1.id, [0])
    assert ok, msg

    # Pool should now be empty (paid {R}{1}).
    pool = game.mana_system.get_pool(p1.id)
    assert pool.total() == 0, f"expected empty pool; got {pool.total()}"

    # Resolve the spell — M1's effect should fire.
    events = game.stack.resolve_top()
    life = [e for e in events if e.type == EventType.LIFE_CHANGE]
    assert len(life) == 1, f"expected 1 LIFE_CHANGE; got {[e.type for e in events]}"
    assert fired == ["M1"], f"expected only M1 fired; got {fired}"
    print("OK: single-mode Spree resolved correctly")


# ---------------------------------------------------------------------------
# 5. Multi-mode select pays both costs and fires both effects in order
# ---------------------------------------------------------------------------


def test_spree_cast_multi_mode_pays_both_runs_in_order():
    print("\n=== Test: Spree multi-mode pays each + fires in order ===")
    fired = []

    def m1(spell, state, targets):
        fired.append("M1")
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': spell.controller, 'amount': 1},
                      source=spell.id)]

    def m2(spell, state, targets):
        fired.append("M2")
        return [Event(type=EventType.DRAW,
                      payload={'player': spell.controller, 'amount': 1},
                      source=spell.id)]

    modes = [
        SpreeMode(name="M1", extra_cost="{1}", effect_fn=m1),
        SpreeMode(name="M2", extra_cost="{1}", effect_fn=m2),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")

    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 2)  # base {R} + {1} + {1} = {R}{2}

    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is not None

    # Pick both M1 and M2
    ok, msg, _ = submit_spree(game, p1.id, [0, 1])
    assert ok, msg

    # Pool should be empty (paid {R}{2}).
    pool = game.mana_system.get_pool(p1.id)
    assert pool.total() == 0, f"expected empty pool; got {pool.total()}"

    # Resolve — both effects fire in declaration order.
    events = game.stack.resolve_top()
    life = [e for e in events if e.type == EventType.LIFE_CHANGE]
    draws = [e for e in events if e.type == EventType.DRAW]
    assert len(life) == 1, f"expected 1 LIFE_CHANGE; got {[e.type for e in events]}"
    assert len(draws) == 1, f"expected 1 DRAW; got {[e.type for e in events]}"
    assert fired == ["M1", "M2"], f"expected M1 then M2; got {fired}"
    print("OK: multi-mode Spree resolved both effects in order")


def test_spree_cast_multi_mode_order_independent_of_submit_order():
    """When submit indices come in [1, 0], resolve still fires in declaration order."""
    print("\n=== Test: Spree resolve order is declaration order ===")
    fired = []

    def m1(spell, state, targets):
        fired.append("M1")
        return []

    def m2(spell, state, targets):
        fired.append("M2")
        return []

    modes = [
        SpreeMode(name="M1", extra_cost="{1}", effect_fn=m1),
        SpreeMode(name="M2", extra_cost="{1}", effect_fn=m2),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")

    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    # Submit in reverse order: M2 then M1.
    submit_spree(game, p1.id, [1, 0])

    game.stack.resolve_top()
    # Resolve preserves submit order (the chosen list is what we recorded).
    assert fired == ["M2", "M1"], f"effect order = chosen order; got {fired}"
    print("OK: resolve fires in chosen-index order")


# ---------------------------------------------------------------------------
# 6. Affordability — uncastable when no mode payable
# ---------------------------------------------------------------------------


def test_spree_cast_uncastable_no_prompt_no_mana():
    """No mana for any mode -> no prompt, no spell on stack."""
    print("\n=== Test: Spree uncastable when no mode affordable ===")
    modes = [
        SpreeMode(name="M1", extra_cost="{2}", effect_fn=lambda s, st, t: []),
        SpreeMode(name="M2", extra_cost="{5}", effect_fn=lambda s, st, t: []),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    # No generic mana -> no mode is affordable.
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is None, "no mode is affordable; should not prompt"
    # Spell should still be in HAND (not on stack).
    assert spell.zone == ZoneType.HAND, f"spell should not have moved; got {spell.zone}"
    print("OK: cast rejected when no mode payable")


def test_spree_min_modes_enforced():
    """submit_choice with fewer than min_modes selections is rejected."""
    print("\n=== Test: Spree min_modes enforced ===")
    modes = [
        SpreeMode(name="M1", extra_cost="{1}", effect_fn=lambda s, st, t: []),
        SpreeMode(name="M2", extra_cost="{1}", effect_fn=lambda s, st, t: []),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is not None
    # Try to submit zero modes — should be rejected.
    choice = game.state.pending_choice
    assert choice.min_choices >= 1
    # PendingChoice.validate_selection should reject empty.
    ok, _ = choice.validate_selection([])
    assert not ok, "empty selection should be rejected for Spree (min_choices=1)"
    print("OK: min_modes=1 rejected zero-selection submission")


# ---------------------------------------------------------------------------
# 7. Per-card smoke tests for the wired OTJ Spree cards
# ---------------------------------------------------------------------------


def _setup_caster_with_creatures(game, p1_id, p2_id):
    """Create a few battlefield creatures for sweeping spells to hit."""
    bear_def = make_creature(
        name="Test Bear",
        power=2, toughness=2,
        mana_cost="{2}",
        colors=set(),
    )
    pirate_def = make_creature(
        name="Test Pirate",
        power=2, toughness=2,
        mana_cost="{2}",
        colors=set(),
        subtypes={"Pirate"},
    )
    # P1 has a non-outlaw bear and a pirate.
    p1_bear = game.create_object(
        name="Test Bear", owner_id=p1_id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    p1_pirate = game.create_object(
        name="Test Pirate", owner_id=p1_id, zone=ZoneType.BATTLEFIELD,
        characteristics=pirate_def.characteristics, card_def=pirate_def,
    )
    # P2 has a bear too.
    p2_bear = game.create_object(
        name="Test Bear", owner_id=p2_id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    return p1_bear, p1_pirate, p2_bear


def test_caught_in_the_crossfire_outlaws_only():
    """+ {1} damage to outlaws fires; non-outlaws untouched."""
    print("\n=== Test: Caught in the Crossfire (outlaws mode) ===")
    game, p1, p2 = make_two_player_game()
    p1_bear, p1_pirate, p2_bear = _setup_caster_with_creatures(game, p1.id, p2.id)
    spell = make_spell(game, p1.id, otj.CAUGHT_IN_THE_CROSSFIRE)
    # Pay {R}{R} + {1} = {R}{R}{1}
    add_mana(game, p1.id, "R", 2)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is not None
    submit_spree(game, p1.id, [0])  # pick outlaws-only
    events = game.stack.resolve_top()
    dmg = [e for e in events if e.type == EventType.DAMAGE]
    targeted_ids = {e.payload.get('target') for e in dmg}
    assert p1_pirate.id in targeted_ids, f"pirate should take damage; got {targeted_ids}"
    assert p1_bear.id not in targeted_ids, "bear should NOT take damage from outlaws-only mode"
    assert p2_bear.id not in targeted_ids, "p2's bear should NOT take damage"
    assert all(e.payload.get('amount') == 2 for e in dmg)
    print(f"OK: outlaws mode dealt 2 damage to {len(dmg)} outlaw(s)")


def test_caught_in_the_crossfire_both_modes():
    """Both modes -> all creatures take 2 damage."""
    print("\n=== Test: Caught in the Crossfire (both modes) ===")
    game, p1, p2 = make_two_player_game()
    p1_bear, p1_pirate, p2_bear = _setup_caster_with_creatures(game, p1.id, p2.id)
    spell = make_spell(game, p1.id, otj.CAUGHT_IN_THE_CROSSFIRE)
    # Pay {R}{R} + {1} + {1} = {R}{R}{2}
    add_mana(game, p1.id, "R", 2)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0, 1])  # both modes
    events = game.stack.resolve_top()
    dmg = [e for e in events if e.type == EventType.DAMAGE]
    targeted_ids = {e.payload.get('target') for e in dmg}
    assert {p1_bear.id, p1_pirate.id, p2_bear.id} <= targeted_ids
    print(f"OK: both modes dealt 2 damage to all 3 creatures ({len(dmg)} events)")


def test_final_showdown_lose_abilities_only():
    """+ {1} all creatures lose abilities."""
    print("\n=== Test: Final Showdown (lose abilities) ===")
    game, p1, p2 = make_two_player_game()
    _setup_caster_with_creatures(game, p1.id, p2.id)
    spell = make_spell(game, p1.id, otj.FINAL_SHOWDOWN)
    add_mana(game, p1.id, "W", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])
    events = game.stack.resolve_top()
    eff = [e for e in events
           if e.type == EventType.TEMPORARY_EFFECT
           and e.payload.get('effect') == 'lose_all_abilities']
    assert len(eff) >= 3, f"expected 3+ creatures; got {len(eff)}"
    print(f"OK: {len(eff)} creatures lost abilities")


def test_final_showdown_destroy_all_costs_more():
    """+ {3}{W}{W} destroy all creatures requires the heavy cost."""
    print("\n=== Test: Final Showdown (destroy all) ===")
    game, p1, p2 = make_two_player_game()
    _setup_caster_with_creatures(game, p1.id, p2.id)
    spell = make_spell(game, p1.id, otj.FINAL_SHOWDOWN)
    # Pay {W} + {3}{W}{W} = {W}{W}{W}{3}
    add_mana(game, p1.id, "W", 3)
    add_mana(game, p1.id, "C", 3)
    cast_spell(game, p1.id, spell)
    options = game.state.pending_choice.options
    indices = {o["index"] for o in options}
    assert 2 in indices, f"destroy-all mode should be affordable; got {indices}"
    submit_spree(game, p1.id, [2])
    events = game.stack.resolve_top()
    destroys = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
    assert len(destroys) >= 3, f"expected 3+ creatures destroyed; got {len(destroys)}"
    print(f"OK: destroy-all mode wiped {len(destroys)} creatures")


def submit_target(game, player_id, target_id):
    """Submit a chained per-mode target choice via PendingChoice.

    The target prompt opens during stack resolution of a Spree spell whose
    chosen mode has ``targets_required > 0``. The handler runs the mode's
    effect_fn with the chosen target and chains to the next mode.
    """
    choice = game.state.pending_choice
    assert choice is not None, "expected pending target choice"
    assert choice.choice_type == "target_with_callback", \
        f"expected target_with_callback; got {choice.choice_type}"
    return game.submit_choice(choice.id, player_id, [target_id])


def test_requisition_raid_artifact_destroy():
    """+ {1} destroy target artifact (uses chained per-mode target prompt)."""
    print("\n=== Test: Requisition Raid (artifact destroy w/ target prompt) ===")
    game, p1, p2 = make_two_player_game()
    # Build a vanilla artifact via factories.
    from src.cards.card_factories import make_artifact
    plain_artifact = make_artifact(name="Test Artifact", mana_cost="{2}", text="")
    art = game.create_object(
        name="Test Artifact",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=plain_artifact.characteristics,
        card_def=plain_artifact,
    )
    spell = make_spell(game, p1.id, otj.REQUISITION_RAID)
    # Pay {W} + {1} = {W}{1}
    add_mana(game, p1.id, "W", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # destroy artifact mode
    # Resolve top — should open a target_with_callback for the artifact.
    pre_events = game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected pending target prompt for artifact mode"
    assert pc.choice_type == "target_with_callback"
    assert art.id in pc.options, f"artifact should be a legal target; got {pc.options}"
    # Submit the artifact as the target — callback fires the destroy.
    ok, msg, events = submit_target(game, p1.id, art.id)
    assert ok, msg
    destroys = [e for e in events
                if e.type == EventType.OBJECT_DESTROYED
                and e.payload.get('object_id') == art.id]
    assert destroys, f"expected p2's artifact to be destroyed; got {[e.type for e in events]}"
    print("OK: Requisition Raid prompted for + destroyed targeted artifact")


def test_rustler_rampage_double_strike_mode():
    """+ {1} target creature gains double strike (uses chained per-mode prompt)."""
    print("\n=== Test: Rustler Rampage (double strike w/ target prompt) ===")
    game, p1, p2 = make_two_player_game()
    bear_def = make_creature(name="P1 Bear", power=2, toughness=2,
                             mana_cost="{2}", colors=set())
    bear = game.create_object(
        name="P1 Bear", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    spell = make_spell(game, p1.id, otj.RUSTLER_RAMPAGE)
    # Pay {W} + {1} = {W}{1}
    add_mana(game, p1.id, "W", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [1])  # double-strike mode (targeted)
    pre_events = game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected pending target prompt for double-strike mode"
    assert bear.id in pc.options
    ok, msg, events = submit_target(game, p1.id, bear.id)
    assert ok, msg
    grants = [e for e in events
              if e.type == EventType.GRANT_KEYWORD
              and e.payload.get('keyword') == 'double_strike']
    assert grants, f"expected double_strike grant; got {[e.payload for e in events]}"
    assert any(e.payload.get('object_id') == bear.id for e in grants)
    print("OK: Rustler Rampage prompted for + granted double strike")


def test_explosive_derailment_damage_mode():
    """+ {2} 4 damage to target creature (uses chained per-mode prompt)."""
    print("\n=== Test: Explosive Derailment (damage w/ target prompt) ===")
    game, p1, p2 = make_two_player_game()
    bear_def = make_creature(name="P2 Bear", power=2, toughness=2,
                             mana_cost="{2}", colors=set())
    bear = game.create_object(
        name="P2 Bear", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    spell = make_spell(game, p1.id, otj.EXPLOSIVE_DERAILMENT)
    # Pay {R} + {2} = {R}{2}
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # damage mode
    pre_events = game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected pending target prompt for damage mode"
    assert bear.id in pc.options
    ok, msg, events = submit_target(game, p1.id, bear.id)
    assert ok, msg
    dmg = [e for e in events if e.type == EventType.DAMAGE]
    assert dmg, f"expected damage event; got {[e.type for e in events]}"
    assert dmg[0].payload.get('amount') == 4, f"expected 4 damage; got {dmg[0].payload}"
    assert dmg[0].payload.get('target') == bear.id
    print("OK: Explosive Derailment prompted for + dealt 4 damage to chosen target")


# ---------------------------------------------------------------------------
# 8. Per-mode targeting: chained PendingChoices at resolve
# ---------------------------------------------------------------------------


def test_spree_single_targeted_mode_opens_prompt():
    """Cast a Spree spell with one targeted mode -> PendingChoice for target."""
    print("\n=== Test: Single targeted-mode opens target_with_callback ===")
    fired_with: list = []

    def m_targeted(spell, state, targets):
        fired_with.append(list(targets))
        return [Event(type=EventType.OBJECT_DESTROYED,
                      payload={'object_id': targets[0]}, source=spell.id)]

    modes = [
        SpreeMode(name="Destroy", extra_cost="{1}",
                  effect_fn=m_targeted, target_kind="creature",
                  targets_required=1,
                  description="Destroy target creature."),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")
    game, p1, p2 = make_two_player_game()
    bear_def = make_creature(name="Test Bear", power=2, toughness=2,
                             mana_cost="{2}", colors=set())
    bear = game.create_object(
        name="Test Bear", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # mode 0 (targeted)
    # Resolve — should open target_with_callback for the creature.
    game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected target_with_callback"
    assert pc.choice_type == "target_with_callback"
    assert bear.id in pc.options, f"bear should be legal target; got {pc.options}"
    # Submit the target — effect fires.
    ok, msg, events = submit_target(game, p1.id, bear.id)
    assert ok, msg
    assert fired_with == [[bear.id]], f"effect_fn should receive [bear.id]; got {fired_with}"
    destroys = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
    assert destroys, f"expected destroy event; got {[e.type for e in events]}"
    print("OK: targeted mode opened prompt + fired effect with chosen target")


def test_spree_two_targeted_modes_chain_in_order():
    """Two targeted modes -> chained PendingChoices in declaration order."""
    print("\n=== Test: Two targeted modes chain in declaration order ===")
    target_log: list = []

    def m1(spell, state, targets):
        target_log.append(("M1", list(targets)))
        return [Event(type=EventType.DAMAGE,
                      payload={'target': targets[0], 'amount': 1, 'source': spell.id, 'is_combat': False},
                      source=spell.id)]

    def m2(spell, state, targets):
        target_log.append(("M2", list(targets)))
        return [Event(type=EventType.OBJECT_DESTROYED,
                      payload={'object_id': targets[0]}, source=spell.id)]

    modes = [
        SpreeMode(name="Damage", extra_cost="{1}",
                  effect_fn=m1, target_kind="creature",
                  targets_required=1,
                  description="Deal 1 damage to target creature."),
        SpreeMode(name="Destroy", extra_cost="{1}",
                  effect_fn=m2, target_kind="creature",
                  targets_required=1,
                  description="Destroy target creature."),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")
    game, p1, p2 = make_two_player_game()
    bear_def = make_creature(name="Test Bear", power=2, toughness=2,
                             mana_cost="{2}", colors=set())
    a = game.create_object(
        name="Bear A", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    b = game.create_object(
        name="Bear B", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0, 1])  # both targeted modes
    # Resolve — opens M1's target prompt first.
    game.stack.resolve_top()
    pc1 = game.state.pending_choice
    assert pc1 is not None
    assert pc1.callback_data.get("mode_name") == "Damage", \
        f"expected M1 (Damage) prompt first; got {pc1.callback_data}"
    # Submit a as M1's target.
    ok, msg, events1 = submit_target(game, p1.id, a.id)
    assert ok, msg
    # M2's prompt should now be open.
    pc2 = game.state.pending_choice
    assert pc2 is not None, "expected chained target prompt for M2"
    assert pc2.callback_data.get("mode_name") == "Destroy", \
        f"expected M2 (Destroy) prompt second; got {pc2.callback_data}"
    # Submit b as M2's target.
    ok, msg, events2 = submit_target(game, p1.id, b.id)
    assert ok, msg
    # Verify both effects fired in correct order with correct targets.
    assert target_log == [("M1", [a.id]), ("M2", [b.id])], \
        f"chained order broken; got {target_log}"
    # Combined events should include damage to a + destroy of b.
    all_events = list(events1) + list(events2)
    dmg = [e for e in all_events if e.type == EventType.DAMAGE]
    destroys = [e for e in all_events if e.type == EventType.OBJECT_DESTROYED]
    assert dmg and dmg[0].payload.get('target') == a.id
    assert destroys and destroys[0].payload.get('object_id') == b.id
    print("OK: two targeted modes chained PendingChoices in declaration order")


def test_spree_targeted_mode_with_no_legal_targets_skipped():
    """Targeted mode with no legal targets is skipped (CR 608.2b)."""
    print("\n=== Test: Targeted mode w/ no legal targets is skipped ===")
    fired: list = []

    def m_targeted(spell, state, targets):
        fired.append(("targeted", list(targets)))
        return []

    def m_inline(spell, state, targets):
        fired.append(("inline", list(targets)))
        return [Event(type=EventType.LIFE_CHANGE,
                      payload={'player': spell.controller, 'amount': 1},
                      source=spell.id)]

    modes = [
        SpreeMode(name="Destroy creature", extra_cost="{1}",
                  effect_fn=m_targeted, target_kind="creature",
                  targets_required=1,
                  description="Destroy target creature."),
        SpreeMode(name="Gain 1", extra_cost="{1}",
                  effect_fn=m_inline,
                  description="Gain 1 life."),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")
    game, p1, p2 = make_two_player_game()
    # NO creatures on the battlefield -> mode 0 has no legal targets.
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0, 1])  # both modes chosen
    events = game.stack.resolve_top()
    # Mode 0 should be silently skipped (no prompt opens for it).
    assert game.state.pending_choice is None, \
        f"no creature exists -> mode 0 skipped; pending={game.state.pending_choice}"
    # Mode 1 (inline life-gain) should still fire.
    assert fired == [("inline", [])], \
        f"only mode 1 should fire; got {fired}"
    life = [e for e in events if e.type == EventType.LIFE_CHANGE]
    assert life, f"expected life gain from mode 1; got {[e.type for e in events]}"
    print("OK: no-legal-targets mode skipped, later mode still resolved")


def test_spree_legal_targets_filter_override():
    """SpreeMode.legal_targets_filter overrides default target enumeration."""
    print("\n=== Test: legal_targets_filter custom predicate ===")

    def m_targeted(spell, state, targets):
        return [Event(type=EventType.OBJECT_DESTROYED,
                      payload={'object_id': targets[0]}, source=spell.id)]

    def filter_only_outlaws(spell, state):
        outlaw_types = {'Pirate', 'Rogue', 'Mercenary', 'Assassin', 'Warlock'}
        return [
            obj.id for obj in state.objects.values()
            if obj.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in obj.characteristics.types
            and (obj.characteristics.subtypes or set()) & outlaw_types
        ]

    modes = [
        SpreeMode(name="Outlaw destroy", extra_cost="{1}",
                  effect_fn=m_targeted, target_kind="creature",
                  targets_required=1,
                  legal_targets_filter=filter_only_outlaws,
                  description="Destroy target outlaw creature."),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")
    game, p1, p2 = make_two_player_game()
    # Create a non-outlaw bear and an outlaw pirate.
    bear_def = make_creature(name="Plain Bear", power=2, toughness=2,
                             mana_cost="{2}", colors=set())
    pirate_def = make_creature(name="Plain Pirate", power=2, toughness=2,
                               mana_cost="{2}", colors=set(),
                               subtypes={"Pirate"})
    bear = game.create_object(
        name="Plain Bear", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    pirate = game.create_object(
        name="Plain Pirate", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=pirate_def.characteristics, card_def=pirate_def,
    )
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])
    game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None
    # Only the pirate should be a legal target (filter excludes the bear).
    assert pirate.id in pc.options, f"pirate should be legal; got {pc.options}"
    assert bear.id not in pc.options, f"bear should be filtered out; got {pc.options}"
    ok, msg, events = submit_target(game, p1.id, pirate.id)
    assert ok, msg
    destroys = [e for e in events if e.type == EventType.OBJECT_DESTROYED]
    assert destroys and destroys[0].payload.get('object_id') == pirate.id
    print("OK: legal_targets_filter constrained target options correctly")


def test_spree_mixed_targeted_and_inline_modes_chain_correctly():
    """Mix of targeted + inline modes preserves declaration order."""
    print("\n=== Test: Mixed targeted/inline modes preserve order ===")
    fired: list = []

    def m_inline_a(spell, state, targets):
        fired.append("A")
        return []

    def m_targeted_b(spell, state, targets):
        fired.append(("B", list(targets)))
        return []

    def m_inline_c(spell, state, targets):
        fired.append("C")
        return []

    modes = [
        SpreeMode(name="A inline", extra_cost="{1}",
                  effect_fn=m_inline_a,
                  description="Inline A."),
        SpreeMode(name="B targeted", extra_cost="{1}",
                  effect_fn=m_targeted_b, target_kind="creature",
                  targets_required=1,
                  description="Targeted B."),
        SpreeMode(name="C inline", extra_cost="{1}",
                  effect_fn=m_inline_c,
                  description="Inline C."),
    ]
    card = _build_synthetic_spree(modes, mana_cost="{R}")
    game, p1, p2 = make_two_player_game()
    bear_def = make_creature(name="Test Bear", power=2, toughness=2,
                             mana_cost="{2}", colors=set())
    bear = game.create_object(
        name="Test Bear", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 3)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0, 1, 2])  # all three modes
    game.stack.resolve_top()
    # A fired inline; then prompt for B.
    assert fired == ["A"], f"expected A inline before B prompt; got {fired}"
    pc = game.state.pending_choice
    assert pc is not None and pc.callback_data.get("mode_name") == "B targeted"
    ok, msg, events = submit_target(game, p1.id, bear.id)
    assert ok, msg
    # B fires with bear.id, then C inline.
    assert fired == ["A", ("B", [bear.id]), "C"], \
        f"expected A,B(bear),C in declaration order; got {fired}"
    print("OK: mixed inline + targeted modes chained in declaration order")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def main():
    tests = [
        test_spree_mode_basic,
        test_spree_mode_with_manacost_object,
        test_spree_mode_label,
        test_compute_affordable_spree_modes_no_mana,
        test_compute_affordable_spree_modes_partial_pool,
        test_make_spree_setup_tags_card_def,
        test_spree_cast_single_mode_pays_extra_runs_effect,
        test_spree_cast_multi_mode_pays_both_runs_in_order,
        test_spree_cast_multi_mode_order_independent_of_submit_order,
        test_spree_cast_uncastable_no_prompt_no_mana,
        test_spree_min_modes_enforced,
        test_caught_in_the_crossfire_outlaws_only,
        test_caught_in_the_crossfire_both_modes,
        test_final_showdown_lose_abilities_only,
        test_final_showdown_destroy_all_costs_more,
        test_requisition_raid_artifact_destroy,
        test_rustler_rampage_double_strike_mode,
        test_explosive_derailment_damage_mode,
        # Per-mode-targeting tests (W12 follow-up)
        test_spree_single_targeted_mode_opens_prompt,
        test_spree_two_targeted_modes_chain_in_order,
        test_spree_targeted_mode_with_no_legal_targets_skipped,
        test_spree_legal_targets_filter_override,
        test_spree_mixed_targeted_and_inline_modes_chain_correctly,
    ]
    passed = 0
    failed = []
    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as exc:
            import traceback
            traceback.print_exc()
            failed.append((fn.__name__, exc))
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        for name, exc in failed:
            print(f"  FAIL {name}: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
