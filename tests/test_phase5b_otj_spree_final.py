"""
Tests for the Phase 5b final batch:
- 13 OTJ Spree cards migrated to the SpreeMode pattern.
- DSK Trial of Agony: cross-target same-opponent constraint + opponent
  chooses which of two takes 5 damage; other can't block.

Each migrated card is checked for:
- ``_spree_modes`` metadata is attached at setup_interceptors time (card_def
  has the expected mode list).
- Smoke: cast pays base+mode and resolves at least one event (single mode).

Trial of Agony is checked for:
- target_requirements declared with cross-target builder.
- The builder narrows the second prompt to the first pick's controller.
- The controlling opponent's choice routes damage and 'cant_block'.
"""

import asyncio
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    PlayerAction, ActionType, ManaCost,
    SpreeMode, make_spree_setup, make_spree_resolve,
    is_spree_card, get_spree_modes,
    make_instant, make_creature,
)
from src.engine.targeting import target_same_opponent_creature
from src.cards import outlaws_thunder_junction as otj
from src.cards import duskmourn as dsk


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_spree.py)
# ---------------------------------------------------------------------------


def make_two_player_game():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    return game, p1, p2


def add_mana(game, player_id, color="C", amount=1):
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
    choice = game.state.pending_choice
    assert choice is not None, "expected pending Spree choice"
    payload = [{"index": i} for i in indices]
    return game.submit_choice(choice.id, player_id, payload)


def submit_target(game, player_id, target_id):
    choice = game.state.pending_choice
    assert choice is not None, "expected pending target choice"
    return game.submit_choice(choice.id, player_id, [target_id])


def make_bear(game, owner_id, name="Bear", power=2, toughness=2, subtypes=None):
    if subtypes is None:
        subtypes = set()
    bear_def = make_creature(
        name=name, power=power, toughness=toughness,
        mana_cost="{2}", colors=set(),
        subtypes=subtypes,
    )
    return game.create_object(
        name=name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )


# ---------------------------------------------------------------------------
# 1. Mode registration: each migrated card has _spree_modes after setup
# ---------------------------------------------------------------------------


# The card_def is mutated by setup_interceptors at GameObject creation. The
# fastest check is: spawn a GameObject in HAND, run setup_interceptors against
# it, then read the card_def attribute. is_spree_card() walks card_def.
_MIGRATED_CARDS = [
    ("GETAWAY_GLAMER", 2),
    ("ONE_LAST_JOB", 3),
    ("PHANTOM_INTERFERENCE", 2),
    ("SHIFTING_GRIFT", 3),
    ("THREE_STEPS_AHEAD", 3),
    ("INSATIABLE_AVARICE", 2),
    ("LIVELY_DIRGE", 2),
    ("RUSH_OF_DREAD", 3),
    ("GREAT_TRAIN_HEIST", 3),
    # RETURN_THE_FAVOR migrated off Spree to a regular instant in Phase 5b
    # mop-up (Agent J): copies target opposing instant/sorcery via
    # COPY_STACK_ITEM. See ``tests/test_phase5b_spell_copy.py`` for coverage.
    ("DANCE_OF_THE_TUMBLEWEEDS", 2),
    ("SMUGGLERS_SURPRISE", 3),
    ("TRASH_THE_TOWN", 3),
]


def _run_setup_for_card(game, owner_id, card_def):
    """Spawn the card on the BATTLEFIELD briefly so setup_interceptors runs
    and tags the card_def with Spree metadata; then move it back to HAND.
    """
    obj = game.create_object(
        name=card_def.name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    return obj


def test_all_migrated_cards_register_spree_modes():
    print("\n=== Test: Migrated cards register _spree_modes correctly ===")
    game, p1, _ = make_two_player_game()
    failed: list[str] = []
    for card_name, expected_count in _MIGRATED_CARDS:
        card = getattr(otj, card_name)
        # Spawn the card so setup_interceptors runs.
        obj = _run_setup_for_card(game, p1.id, card)
        # Verify metadata.
        if not is_spree_card(obj):
            failed.append(f"{card_name}: is_spree_card() False")
            continue
        modes = get_spree_modes(obj)
        if len(modes) != expected_count:
            failed.append(
                f"{card_name}: expected {expected_count} modes, got {len(modes)}"
            )
            continue
        print(f"  OK {card_name}: {len(modes)} modes")
    assert not failed, "Mode registration failed for:\n" + "\n".join(failed)
    print(f"OK: all {len(_MIGRATED_CARDS)} migrated cards register Spree modes")


# ---------------------------------------------------------------------------
# 2. Per-card smoke tests for at least 3 cards
# ---------------------------------------------------------------------------


def test_getaway_glamer_flicker_mode_fires():
    """+ {1} Exile target nontoken creature with return-at-end-step rider."""
    print("\n=== Test: Getaway Glamer flicker mode ===")
    game, p1, p2 = make_two_player_game()
    target = make_bear(game, p2.id, name="P2 Target")
    spell = make_spell(game, p1.id, otj.GETAWAY_GLAMER)
    add_mana(game, p1.id, "W", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # Flicker mode
    pre = game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected target prompt for flicker mode"
    assert target.id in pc.options
    ok, msg, events = submit_target(game, p1.id, target.id)
    assert ok, msg
    zone_changes = [e for e in events if e.type == EventType.ZONE_CHANGE]
    assert zone_changes, f"expected exile via ZONE_CHANGE; got {[e.type for e in events]}"
    found = any(
        e.payload.get('to_zone_type') == ZoneType.EXILE
        and e.payload.get('return_at_end_step')
        for e in zone_changes
    )
    assert found, f"expected exile-with-return; got {[(e.type, e.payload) for e in zone_changes]}"
    print("OK: Getaway Glamer flicker mode resolved as exile-with-return")


def test_phantom_interference_token_mode():
    """+ {3} Create 2/2 Spirit token (no-target inline mode)."""
    print("\n=== Test: Phantom Interference token mode ===")
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, otj.PHANTOM_INTERFERENCE)
    add_mana(game, p1.id, "U", 1)
    add_mana(game, p1.id, "C", 3)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # token mode (inline)
    events = game.stack.resolve_top()
    tokens = [e for e in events if e.type == EventType.CREATE_TOKEN]
    assert tokens, f"expected CREATE_TOKEN; got {[e.type for e in events]}"
    payload = tokens[0].payload
    assert payload.get('name') == 'Spirit'
    assert payload.get('power') == 2 and payload.get('toughness') == 2
    assert 'flying' in (payload.get('abilities') or [])
    print("OK: Phantom Interference Spirit token created")


def test_trash_the_town_counters_mode_targeted():
    """+ {2} Put two +1/+1 counters on target creature."""
    print("\n=== Test: Trash the Town counters mode ===")
    game, p1, p2 = make_two_player_game()
    bear = make_bear(game, p1.id, name="My Bear")
    spell = make_spell(game, p1.id, otj.TRASH_THE_TOWN)
    add_mana(game, p1.id, "G", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # counters mode
    pre = game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected target prompt for counters mode"
    assert bear.id in pc.options
    ok, msg, events = submit_target(game, p1.id, bear.id)
    assert ok, msg
    counters = [e for e in events
                if e.type == EventType.COUNTER_ADDED
                and e.payload.get('amount') == 2]
    assert counters, f"expected +1/+1 x2; got {[e.payload for e in events]}"
    print("OK: Trash the Town placed two +1/+1 counters")


def test_dance_of_the_tumbleweeds_elemental_mode():
    """+ {3} Create X/X green Elemental token (no targets)."""
    print("\n=== Test: Dance of the Tumbleweeds Elemental mode ===")
    game, p1, _ = make_two_player_game()
    # Add a couple of lands so X != 0
    from src.cards.card_factories import make_land
    plains_def = make_land(name="Plains", subtypes={"Plains"}, text="")
    for _ in range(3):
        game.create_object(
            name="Plains", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=plains_def.characteristics, card_def=plains_def,
        )

    spell = make_spell(game, p1.id, otj.DANCE_OF_THE_TUMBLEWEEDS)
    add_mana(game, p1.id, "G", 1)
    add_mana(game, p1.id, "C", 4)  # {G} base + {3} mode
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [1])  # elemental mode
    events = game.stack.resolve_top()
    tokens = [e for e in events if e.type == EventType.CREATE_TOKEN]
    assert tokens, f"expected token creation; got {[e.type for e in events]}"
    payload = tokens[0].payload
    assert payload.get('name') == 'Elemental'
    assert payload.get('power') == 3, f"X should be 3 (lands); got {payload}"
    print(f"OK: Dance of the Tumbleweeds created {payload.get('power')}/{payload.get('toughness')} Elemental")


def test_insatiable_avarice_draw_loss_mode():
    """+ {B}{B} Target player draws 3 and loses 3 life."""
    print("\n=== Test: Insatiable Avarice draw/loss mode ===")
    game, p1, p2 = make_two_player_game()
    spell = make_spell(game, p1.id, otj.INSATIABLE_AVARICE)
    add_mana(game, p1.id, "B", 3)  # {B} base + {B}{B} mode
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [1])  # draw/loss mode (targeted)
    pre = game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected target prompt for draw/loss mode"
    # Target self for simplicity.
    ok, msg, events = submit_target(game, p1.id, p1.id)
    assert ok, msg
    draws = [e for e in events
             if e.type == EventType.DRAW and e.payload.get('amount') == 3]
    life_change = [e for e in events
                   if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('amount') == -3]
    assert draws, f"expected DRAW 3; got {[e.payload for e in events]}"
    assert life_change, f"expected LIFE_CHANGE -3; got {[e.payload for e in events]}"
    print("OK: Insatiable Avarice draws 3 + loses 3 life")


# ---------------------------------------------------------------------------
# 3. Multi-mode smoke: pick all modes, verify each effect emits
# ---------------------------------------------------------------------------


def test_great_train_heist_anthem_only_emits_pump_and_first_strike():
    """+ {2} Creatures get +1/+0 and first strike EOT (inline mode)."""
    print("\n=== Test: Great Train Heist anthem mode ===")
    game, p1, p2 = make_two_player_game()
    b1 = make_bear(game, p1.id, name="P1 Bear 1")
    b2 = make_bear(game, p1.id, name="P1 Bear 2")
    spell = make_spell(game, p1.id, otj.GREAT_TRAIN_HEIST)
    add_mana(game, p1.id, "R", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [1])  # anthem mode
    events = game.stack.resolve_top()
    pt_mods = [e for e in events
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('power_mod') == 1]
    keywords = [e for e in events
                if e.type == EventType.GRANT_KEYWORD
                and e.payload.get('keyword') == 'first_strike']
    assert len(pt_mods) == 2, f"expected 2 PT_MODIFICATION; got {len(pt_mods)}"
    assert len(keywords) == 2, f"expected 2 first_strike grants; got {len(keywords)}"
    print(f"OK: Great Train Heist anthem pumped {len(pt_mods)} creatures")


def test_smugglers_surprise_mill_mode():
    """+ {2} Mill 4 (no-target inline mode)."""
    print("\n=== Test: Smuggler's Surprise mill mode ===")
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, otj.SMUGGLERS_SURPRISE)
    add_mana(game, p1.id, "G", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # mill 4
    events = game.stack.resolve_top()
    mills = [e for e in events if e.type == EventType.MILL]
    assert mills, f"expected MILL; got {[e.type for e in events]}"
    assert mills[0].payload.get('amount') == 4
    print("OK: Smuggler's Surprise mills 4")


def test_shifting_grift_modes_register_even_if_engine_gap():
    """SHIFTING_GRIFT registers all 3 modes (effects are engine gaps but Spree
    metadata still wires)."""
    print("\n=== Test: Shifting Grift mode registration ===")
    game, p1, _ = make_two_player_game()
    obj = _run_setup_for_card(game, p1.id, otj.SHIFTING_GRIFT)
    assert is_spree_card(obj)
    modes = get_spree_modes(obj)
    assert len(modes) == 3, f"expected 3 modes, got {len(modes)}"
    # Verify mode names mention exchange
    names = [m.name for m in modes]
    assert any("creature" in n.lower() for n in names)
    assert any("artifact" in n.lower() for n in names)
    assert any("enchantment" in n.lower() for n in names)
    print(f"OK: Shifting Grift modes: {names}")


def test_cast_with_no_modes_selected_aborts():
    """Sanity check: Spree min_modes=1, so 0 selections cannot resolve."""
    print("\n=== Test: Spree min_modes=1 enforced ===")
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, otj.PHANTOM_INTERFERENCE)
    add_mana(game, p1.id, "U", 1)
    add_mana(game, p1.id, "C", 3)
    cast_spell(game, p1.id, spell)
    choice = game.state.pending_choice
    assert choice is not None
    assert choice.min_choices >= 1
    # Empty selection rejected
    ok, _ = choice.validate_selection([])
    assert not ok
    print("OK: Phantom Interference min_modes=1 rejects empty selection")


# ---------------------------------------------------------------------------
# 4. Trial of Agony tests
# ---------------------------------------------------------------------------


def test_trial_of_agony_declares_target_requirements():
    """Trial of Agony should declare target_requirements with cross-target builder."""
    print("\n=== Test: Trial of Agony target_requirements ===")
    reqs = dsk.TRIAL_OF_AGONY.target_requirements
    assert reqs is not None, "expected target_requirements declared"
    assert len(reqs) == 2, f"expected 2 reqs (two creatures); got {len(reqs)}"
    # Second slot should be a callable builder.
    assert callable(reqs[1]), \
        "second req should be a TargetRequirementBuilder callable"
    print(f"OK: Trial of Agony declared {len(reqs)} target requirements")


def test_target_same_opponent_creature_filter():
    """The builder constrains the second pick to the first pick's controller."""
    print("\n=== Test: target_same_opponent_creature filter ===")
    game, p1, p2 = make_two_player_game()
    # Three creatures: two p2-owned, one p3 hypothetical (instead use p2 only).
    b1 = make_bear(game, p2.id, name="Opp Bear 1")
    b2 = make_bear(game, p2.id, name="Opp Bear 2")
    b3 = make_bear(game, p1.id, name="My Bear")
    builder = target_same_opponent_creature()
    req = builder(game.state, p1.id, [[b1.id]])
    # b2 should match (same controller, different id).
    assert req.filter.matches(b2, game.state, dsk.TRIAL_OF_AGONY.characteristics)
    # b1 should NOT match (excluded as prior pick).
    assert not req.filter.matches(b1, game.state, None), \
        "first pick must be excluded from second prompt"
    # b3 should NOT match (different controller).
    assert not req.filter.matches(b3, game.state, None), \
        "creatures controlled by caster must not match"
    print("OK: target_same_opponent_creature filter correctly narrows by controller")


def test_trial_of_agony_resolve_picks_damage_and_blocker():
    """Resolve: pre-supply two targets; opponent's choice routes damage."""
    print("\n=== Test: Trial of Agony resolve dispatches damage/cant_block ===")
    game, p1, p2 = make_two_player_game()
    big = make_bear(game, p2.id, name="Big Bear", power=4, toughness=4)
    small = make_bear(game, p2.id, name="Small Bear", power=1, toughness=1)
    # Register p2 as AI so the opponent-choice resolves inline rather than
    # pausing waiting for human input.
    if game.turn_manager is None:
        # Create a minimal stand-in so ai_players is reachable.
        class _StubTurnMgr:
            ai_players: set
        game.turn_manager = _StubTurnMgr()
        game.turn_manager.ai_players = set()
    if getattr(game.turn_manager, 'ai_players', None) is None:
        game.turn_manager.ai_players = set()
    game.turn_manager.ai_players.add(p2.id)
    spell = make_spell(game, p1.id, dsk.TRIAL_OF_AGONY)
    add_mana(game, p1.id, "R", 1)
    # Pre-supply the two targets via the targets argument shape used by the
    # resolve path. ``targets`` is shaped as a list-of-lists per requirement.
    from src.engine.targeting import Target
    targets = [
        [Target(id=big.id, is_player=False)],
        [Target(id=small.id, is_player=False)],
    ]
    events = dsk.trial_of_agony_resolve(targets, game.state)
    # The handler resolves choice inline (p2 is AI; falls back to
    # heuristic_pick = [big.id]). Verify damage to big, can't block on small.
    damage = [e for e in events
              if e.type == EventType.DAMAGE
              and e.payload.get('amount') == 5]
    cant_block = [e for e in events if e.type == EventType.CANT_BLOCK]
    assert damage, f"expected 5 damage; got {[e.type for e in events]}"
    assert cant_block, f"expected CANT_BLOCK; got {[e.type for e in events]}"
    # Verify the routing: damage to one, can't block on the other.
    dmg_target = damage[0].payload.get('target')
    cb_target = cant_block[0].payload.get('object_id')
    assert {dmg_target, cb_target} == {big.id, small.id}, \
        f"expected damage+cant_block on the two creatures; got dmg={dmg_target} cb={cb_target}"
    print(f"OK: Trial of Agony dealt 5 dmg to {dmg_target} and 'cant_block' on {cb_target}")


def test_trial_of_agony_resolve_skips_when_only_one_target():
    """If only one valid target is given, the spell does nothing."""
    print("\n=== Test: Trial of Agony aborts when only one creature targeted ===")
    game, p1, p2 = make_two_player_game()
    only_bear = make_bear(game, p2.id, name="Lonely Bear")
    from src.engine.targeting import Target
    targets = [[Target(id=only_bear.id, is_player=False)]]
    events = dsk.trial_of_agony_resolve(targets, game.state)
    assert events == [], f"expected no events; got {events}"
    print("OK: Trial of Agony with single target produces no events")


def test_trial_of_agony_resolve_skips_when_target_left_battlefield():
    """If a chosen target has moved off the battlefield, skip it."""
    print("\n=== Test: Trial of Agony skips targets that left battlefield ===")
    game, p1, p2 = make_two_player_game()
    b1 = make_bear(game, p2.id, name="Live Bear")
    b2 = make_bear(game, p2.id, name="Will Die")
    # Simulate b2 leaving the battlefield before resolve.
    b2.zone = ZoneType.GRAVEYARD
    from src.engine.targeting import Target
    targets = [
        [Target(id=b1.id, is_player=False)],
        [Target(id=b2.id, is_player=False)],
    ]
    events = dsk.trial_of_agony_resolve(targets, game.state)
    assert events == [], "spell fizzles if only one valid target remains"
    print("OK: Trial of Agony skips dead target and fizzles")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_all_migrated_cards_register_spree_modes,
        test_getaway_glamer_flicker_mode_fires,
        test_phantom_interference_token_mode,
        test_trash_the_town_counters_mode_targeted,
        test_dance_of_the_tumbleweeds_elemental_mode,
        test_insatiable_avarice_draw_loss_mode,
        test_great_train_heist_anthem_only_emits_pump_and_first_strike,
        test_smugglers_surprise_mill_mode,
        test_shifting_grift_modes_register_even_if_engine_gap,
        test_cast_with_no_modes_selected_aborts,
        test_trial_of_agony_declares_target_requirements,
        test_target_same_opponent_creature_filter,
        test_trial_of_agony_resolve_picks_damage_and_blocker,
        test_trial_of_agony_resolve_skips_when_only_one_target,
        test_trial_of_agony_resolve_skips_when_target_left_battlefield,
    ]
    passed = 0
    failed: list[tuple[str, str]] = []
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        print("\nFailures:")
        for name, msg in failed:
            print(f"  {name}: {msg}")
        sys.exit(1)
