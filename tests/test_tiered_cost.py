"""
Tests for the FIN Tiered cost mechanic.

Covers:
- TierDefinition dataclass
- compute_affordable_tiers (filtering by mana the caster can pay)
- make_tiered_setup: prompts the player on cast and records the choice
- make_tiered_resolve: emits the chosen tier's effect events
- All five wired FIN cards (Restoration Magic, Fire Magic, Thunder Magic,
  Ice Magic, Tifa's Limit Break)
- Insufficient mana -> tier choice filters to affordable tiers (no fizzle)
- Multi-tier selection -> all chosen tier effects fire in order
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
    TierDefinition, make_tiered_setup, make_tiered_resolve,
    compute_affordable_tiers, get_chosen_tier_index,
    get_chosen_tier_indices, clear_chosen_tier,
    make_instant, make_creature,
)
from src.cards import final_fantasy as ff


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
    """Drive a CAST_SPELL action and emit the resulting events.

    Mirrors what the priority loop does in production: ``_handle_cast_spell``
    returns the CAST event(s) which the loop then emits through the pipeline
    (so REACT-on-CAST interceptors fire). Direct callers must emit too,
    otherwise the tiered prompt never opens.
    """
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=player_id,
        card_id=spell_obj.id,
    )
    cast_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    emitted = []
    for ev in cast_events:
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


def submit_tier(game, player_id, tier_index):
    """Submit a tier choice via the modal-choice path."""
    choice = game.state.pending_choice
    assert choice is not None, "expected pending tier choice"
    return game.submit_choice(choice.id, player_id, [{"index": tier_index}])


# ---------------------------------------------------------------------------
# 1. TierDefinition basic shape
# ---------------------------------------------------------------------------


def test_tier_definition_basic():
    print("\n=== Test: TierDefinition basic ===")
    tier = TierDefinition(
        name="Cure",
        extra_cost="{1}",
        effect_fn=lambda obj, state: [],
        description="Hexproof + indestructible",
    )
    assert tier.name == "Cure"
    cost = tier.resolved_extra_cost()
    assert cost.generic == 1, f"expected generic 1, got {cost.generic}"
    assert not cost.is_free()

    free = TierDefinition(name="Tier 0", extra_cost="{0}", effect_fn=lambda *a: [])
    assert free.resolved_extra_cost().is_free()
    print("OK: TierDefinition parses extra_cost correctly")


def test_tier_definition_with_manacost_object():
    """extra_cost can be a ManaCost instance (not just a string)."""
    print("\n=== Test: TierDefinition accepts ManaCost objects ===")
    cost = ManaCost(generic=2, white=1)
    tier = TierDefinition(name="X", extra_cost=cost, effect_fn=lambda *a: [])
    out = tier.resolved_extra_cost()
    assert out.generic == 2
    assert out.white == 1
    print("OK: ManaCost objects pass through")


# ---------------------------------------------------------------------------
# 2. Affordability
# ---------------------------------------------------------------------------


def test_compute_affordable_tiers_free_only():
    """With no mana, only the {0} tier is affordable."""
    print("\n=== Test: compute_affordable_tiers (no mana) ===")
    game, p1, _ = make_two_player_game()
    tiers = [
        TierDefinition(name="A", extra_cost="{0}", effect_fn=lambda *a: []),
        TierDefinition(name="B", extra_cost="{2}", effect_fn=lambda *a: []),
        TierDefinition(name="C", extra_cost="{5}{R}", effect_fn=lambda *a: []),
    ]
    # No lands and no pool -> only the free tier is affordable.
    aff = compute_affordable_tiers(tiers, game.state, p1.id)
    assert [name for _, t in aff for name in [t.name]] == ["A"], \
        f"expected only the free tier; got {[t.name for _, t in aff]}"
    print("OK: only free tier affordable on empty pool")


def test_compute_affordable_tiers_with_pool():
    """With {2} in pool, tiers <= {2} are affordable."""
    print("\n=== Test: compute_affordable_tiers (pool has {2}) ===")
    game, p1, _ = make_two_player_game()
    add_mana(game, p1.id, "C", 2)
    tiers = [
        TierDefinition(name="A", extra_cost="{0}", effect_fn=lambda *a: []),
        TierDefinition(name="B", extra_cost="{2}", effect_fn=lambda *a: []),
        TierDefinition(name="C", extra_cost="{5}", effect_fn=lambda *a: []),
    ]
    aff = compute_affordable_tiers(tiers, game.state, p1.id)
    names = [t.name for _, t in aff]
    assert "A" in names
    assert "B" in names
    assert "C" not in names, f"C should be unaffordable; got {names}"
    print("OK: tiers filtered to affordable subset")


# ---------------------------------------------------------------------------
# 3. make_tiered_setup integration with cast pipeline (synthetic spell)
# ---------------------------------------------------------------------------


def _build_synthetic_card(tiers):
    """Synthetic instant whose tier effects record their tier id."""
    return make_instant(
        name="Synthetic Tiered Spell",
        mana_cost="{0}",
        colors={Color.RED},
        text="Tiered (Choose one additional cost.)",
        setup_interceptors=lambda obj, state: make_tiered_setup(obj, tiers=tiers),
        resolve=make_tiered_resolve(tiers),
    )


def test_tiered_cast_chooses_tier_ii_pays_extra_and_runs_effect():
    """Casting the synthetic spell with {2} extra in pool, choosing Tier II,
    deducts the extra cost and yields the Tier II effect events."""
    print("\n=== Test: cast picks Tier II ===")
    fired = []

    def t1(obj, state):
        fired.append("T1")
        return []

    def t2(obj, state):
        fired.append("T2")
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1})]

    def t3(obj, state):
        fired.append("T3")
        return []

    tiers = [
        TierDefinition(name="One",   extra_cost="{0}", effect_fn=t1),
        TierDefinition(name="Two",   extra_cost="{2}", effect_fn=t2),
        TierDefinition(name="Three", extra_cost="{5}", effect_fn=t3),
    ]
    card = _build_synthetic_card(tiers)

    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "C", 2)  # Just enough for Tier II's extra cost
    pool_before = game.mana_system.get_pool(p1.id)
    print(f"pool before cast: total={pool_before.total()}")

    cast_spell(game, p1.id, spell)
    # We should be parked on a tier choice.
    assert game.state.pending_choice is not None
    assert game.state.pending_choice.callback_data.get("tiered") is True
    options = game.state.pending_choice.options
    affordable_indices = sorted(o["index"] for o in options)
    print(f"affordable tier indices: {affordable_indices}")
    assert 0 in affordable_indices and 1 in affordable_indices
    # Tier III ({5}) is not affordable.
    assert 2 not in affordable_indices

    ok, msg, _ = submit_tier(game, p1.id, 1)
    assert ok, msg

    # Pool should now be empty (Tier II ate the {2}).
    pool_after = game.mana_system.get_pool(p1.id)
    assert pool_after.total() == 0, f"expected empty pool; got {pool_after.total()}"

    # Resolve the spell — Tier II's effect_fn should fire.
    events = game.stack.resolve_top()
    assert any(e.type == EventType.DRAW for e in events), \
        f"expected DRAW from Tier II; got {[e.type for e in events]}"
    assert fired == ["T2"], f"expected only T2 to fire; got {fired}"
    print("OK: Tier II selected and resolved")


def test_tiered_cast_tier_i_only_no_extra_cost_no_extra_effect():
    """Choosing Tier I (free) deducts no extra mana and emits Tier I's events."""
    print("\n=== Test: cast picks Tier I (free) ===")
    fired = []

    def t1(obj, state):
        fired.append("T1")
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1})]

    def t2(obj, state):
        fired.append("T2")
        return []

    tiers = [
        TierDefinition(name="One", extra_cost="{0}", effect_fn=t1),
        TierDefinition(name="Two", extra_cost="{3}", effect_fn=t2),
    ]
    card = _build_synthetic_card(tiers)

    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "C", 3)  # Enough to make both tiers affordable.
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is not None

    submit_tier(game, p1.id, 0)
    pool_after = game.mana_system.get_pool(p1.id)
    assert pool_after.total() == 3, f"Tier I should not deduct; pool={pool_after.total()}"

    events = game.stack.resolve_top()
    assert any(e.type == EventType.LIFE_CHANGE for e in events)
    assert fired == ["T1"]
    print("OK: Tier I chosen, no extra cost paid")


def test_tiered_cast_insufficient_mana_filters_to_affordable_tiers():
    """When mana is insufficient for an upper tier, that option is filtered out."""
    print("\n=== Test: insufficient mana filters tiers ===")
    tiers = [
        TierDefinition(name="One",   extra_cost="{0}", effect_fn=lambda o, s: []),
        TierDefinition(name="Two",   extra_cost="{2}", effect_fn=lambda o, s: []),
        TierDefinition(name="Three", extra_cost="{5}{R}", effect_fn=lambda o, s: []),
    ]
    card = _build_synthetic_card(tiers)

    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    # No mana -> only free tier is affordable -> auto-resolved without prompt.
    cast_spell(game, p1.id, spell)
    # auto-pick when only one tier is legal (free): no prompt
    assert game.state.pending_choice is None, "should auto-pick the only legal tier"
    indices = get_chosen_tier_indices(game.state, spell.id)
    assert indices == [0], f"expected auto-picked index 0; got {indices}"
    print("OK: only free tier auto-picked")


def test_tiered_multi_select_runs_all_effects_in_order():
    """When max_choices > 1, multiple tiers can be selected; effects fire in order."""
    print("\n=== Test: multi-select tiers fire in order ===")
    fired = []

    def make_fn(label):
        def fn(obj, state):
            fired.append(label)
            return []
        return fn

    tiers = [
        TierDefinition(name="A", extra_cost="{0}", effect_fn=make_fn("A")),
        TierDefinition(name="B", extra_cost="{1}", effect_fn=make_fn("B")),
        TierDefinition(name="C", extra_cost="{2}", effect_fn=make_fn("C")),
    ]
    card = make_instant(
        name="Multi Tier Spell",
        mana_cost="{0}",
        colors={Color.RED},
        text="Tiered.",
        setup_interceptors=lambda obj, state: make_tiered_setup(
            obj, tiers=tiers, min_choices=1, max_choices=3,
        ),
        resolve=make_tiered_resolve(tiers),
    )

    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, card)
    add_mana(game, p1.id, "C", 3)  # Enough for B+C combined.
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is not None

    # Select tiers 0, 1, 2 — all of A/B/C.
    ok, msg, _ = game.submit_choice(
        game.state.pending_choice.id,
        p1.id,
        [{"index": 0}, {"index": 1}, {"index": 2}],
    )
    assert ok, msg
    indices = get_chosen_tier_indices(game.state, spell.id)
    assert indices == [0, 1, 2], f"expected all three; got {indices}"

    game.stack.resolve_top()
    assert fired == ["A", "B", "C"], f"effects not in order: {fired}"
    print("OK: multi-select fires effects in order")


# ---------------------------------------------------------------------------
# 4. Wired FIN cards (one test each)
# ---------------------------------------------------------------------------


def _cast_fin_tiered(card_def, color="W", extra_mana=0):
    """Boilerplate: build a 2-player game, cast the FIN card with given mana."""
    game, p1, p2 = make_two_player_game()

    # Give the caster a creature on the battlefield to act as a target sink.
    target_def = make_creature(
        name="Test Bear",
        power=2, toughness=2,
        mana_cost="{2}",
        colors=set(),
    )
    game.create_object(
        name="Test Bear",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=target_def.characteristics,
        card_def=target_def,
    )
    # Give the opponent a creature too, for damage-targeting tiers.
    enemy = game.create_object(
        name="Enemy Bear",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=target_def.characteristics,
        card_def=target_def,
    )

    spell = make_spell(game, p1.id, card_def)
    # Give mana for both base cost and extra cost. We add generic mana via
    # produce_mana; the priority handler will consume base cost first.
    base = ManaCost.parse(card_def.mana_cost or "")
    total_extra = extra_mana
    total_colorless = base.generic + total_extra
    if total_colorless > 0:
        add_mana(game, p1.id, "C", total_colorless)
    # Add the colored mana from the printed cost.
    if base.white:
        add_mana(game, p1.id, "W", base.white)
    if base.blue:
        add_mana(game, p1.id, "U", base.blue)
    if base.red:
        add_mana(game, p1.id, "R", base.red)
    if base.green:
        add_mana(game, p1.id, "G", base.green)
    if base.black:
        add_mana(game, p1.id, "B", base.black)
    return game, p1, p2, spell, enemy


def test_restoration_magic_cure():
    """Restoration Magic: pick Tier I (Cure, {0}). Permanent gains hexproof+indestructible."""
    print("\n=== Test: Restoration Magic Cure (Tier I) ===")
    game, p1, _, spell, _ = _cast_fin_tiered(ff.RESTORATION_MAGIC, extra_mana=0)
    cast_spell(game, p1.id, spell)
    # With {0} pool extra, only Tier I is affordable -> auto-pick.
    assert game.state.pending_choice is None
    indices = get_chosen_tier_indices(game.state, spell.id)
    assert indices == [0]
    events = game.stack.resolve_top()
    keyword_events = [e for e in events if e.type == EventType.GRANT_KEYWORD]
    assert len(keyword_events) >= 2, f"expected 2 GRANT_KEYWORD events; got {len(keyword_events)}"
    keywords = {e.payload.get('keyword') for e in keyword_events}
    assert 'hexproof' in keywords and 'indestructible' in keywords
    print("OK: Cure granted hexproof + indestructible")


def test_restoration_magic_cura():
    """Restoration Magic Cura ({1}): also gain 3 life."""
    print("\n=== Test: Restoration Magic Cura (Tier II) ===")
    game, p1, _, spell, _ = _cast_fin_tiered(ff.RESTORATION_MAGIC, extra_mana=1)
    cast_spell(game, p1.id, spell)
    # Tier II affordable; we should be prompted (Tier I + Tier II both legal).
    assert game.state.pending_choice is not None
    submit_tier(game, p1.id, 1)
    events = game.stack.resolve_top()
    life_events = [e for e in events if e.type == EventType.LIFE_CHANGE]
    assert any(e.payload.get('amount') == 3 for e in life_events), \
        f"expected +3 life from Cura; got {[e.payload for e in life_events]}"
    print("OK: Cura gained 3 life on top of Cure effect")


def test_fire_magic_fira():
    """Fire Magic Fira ({2}): deals 2 damage to each creature."""
    print("\n=== Test: Fire Magic Fira (Tier II) ===")
    game, p1, p2, spell, _ = _cast_fin_tiered(ff.FIRE_MAGIC, extra_mana=2)
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is not None
    submit_tier(game, p1.id, 1)
    events = game.stack.resolve_top()
    dmg = [e for e in events if e.type == EventType.DAMAGE]
    assert len(dmg) >= 2, f"expected damage to each creature; got {len(dmg)}"
    assert all(e.payload.get('amount') == 2 for e in dmg), \
        f"expected amount=2 for each; got {[e.payload for e in dmg]}"
    print(f"OK: Fira dealt 2 to {len(dmg)} creatures")


def test_thunder_magic_thunder_minimum():
    """Thunder Magic with no extra mana picks Tier I (Thunder = 2 dmg target)."""
    print("\n=== Test: Thunder Magic Thunder (Tier I, no extra) ===")
    game, p1, _, spell, _ = _cast_fin_tiered(ff.THUNDER_MAGIC, extra_mana=0)
    cast_spell(game, p1.id, spell)
    # Only Tier I free -> auto-resolves.
    assert game.state.pending_choice is None
    events = game.stack.resolve_top()
    dmg = [e for e in events if e.type == EventType.DAMAGE]
    assert len(dmg) == 1, f"expected one DAMAGE; got {len(dmg)}"
    assert dmg[0].payload.get('amount') == 2
    print("OK: Thunder dealt 2 to target")


def test_ice_magic_blizzard():
    """Ice Magic Blizzard ({0}): bounce target creature."""
    print("\n=== Test: Ice Magic Blizzard (Tier I) ===")
    game, p1, _, spell, enemy = _cast_fin_tiered(ff.ICE_MAGIC, extra_mana=0)
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is None  # Only Tier I affordable
    events = game.stack.resolve_top()
    # Filter to BOUNCE-style ZONE_CHANGEs (spell self-cleanup also emits ZONE_CHANGE).
    bounce = [
        e for e in events
        if e.type == EventType.ZONE_CHANGE
        and e.payload.get('from_zone') == ZoneType.BATTLEFIELD
        and e.payload.get('to_zone') == ZoneType.HAND
    ]
    assert len(bounce) == 1, (
        f"expected one bounce; got {len(bounce)} "
        f"(events: {[e.payload for e in events if e.type==EventType.ZONE_CHANGE]})"
    )
    print("OK: Blizzard bounced target to hand")


def test_tifas_limit_break_somersault():
    """Tifa's Limit Break Somersault ({0}): +2/+2 EOT to your creature."""
    print("\n=== Test: Tifa's Limit Break Somersault (Tier I) ===")
    game, p1, _, spell, _ = _cast_fin_tiered(ff.TIFAS_LIMIT_BREAK, extra_mana=0)
    cast_spell(game, p1.id, spell)
    assert game.state.pending_choice is None
    events = game.stack.resolve_top()
    pt = [e for e in events if e.type == EventType.PT_MODIFICATION]
    assert len(pt) == 1, f"expected one PT_MODIFICATION; got {len(pt)}"
    assert pt[0].payload.get('power_mod') == 2
    assert pt[0].payload.get('toughness_mod') == 2
    print("OK: Somersault granted +2/+2")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def main():
    tests = [
        test_tier_definition_basic,
        test_tier_definition_with_manacost_object,
        test_compute_affordable_tiers_free_only,
        test_compute_affordable_tiers_with_pool,
        test_tiered_cast_chooses_tier_ii_pays_extra_and_runs_effect,
        test_tiered_cast_tier_i_only_no_extra_cost_no_extra_effect,
        test_tiered_cast_insufficient_mana_filters_to_affordable_tiers,
        test_tiered_multi_select_runs_all_effects_in_order,
        test_restoration_magic_cure,
        test_restoration_magic_cura,
        test_fire_magic_fira,
        test_thunder_magic_thunder_minimum,
        test_ice_magic_blizzard,
        test_tifas_limit_break_somersault,
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
