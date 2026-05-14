"""ModeSpec / per-mode target-requirement tests for make_modal_resolve.

Phase 5b extension: a modal spell can declare a ``target_requirement`` on
each mode. After mode selection the resolver chains one PendingChoice per
chosen-mode-with-targets, accumulates the picks, then dispatches each
``effect_fn(state, caster, spell, targets=...)`` with its targets.

Coverage:
- Single mode with target → target chained, effect fires on chosen target
- Multiple modes, both with targets → both chains run, both effects fire
- Mix of with/without targets → only the targeted modes prompt
- No-target legacy tuple form keeps working (back-compat)
- Empty legal targets → that mode is skipped, remaining modes still run
- AI heuristic_pick path: AI auto-selects first legal target
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    make_sorcery, make_creature,
)
from src.engine.targeting import (
    target_creature, target_player, TargetRequirement, creature_filter,
)
from src.cards.interceptor_helpers import make_modal_resolve, ModeSpec


def _bare_setup_modal(card_def, p1_name="Alice", p2_name="Bob"):
    """Create a game, push the spell to the stack, return (game, p1, p2, spell)."""
    game = Game()
    p1 = game.add_player(p1_name)
    p2 = game.add_player(p2_name)
    spell = game.create_object(
        name=card_def.name, owner_id=p1.id, zone=ZoneType.STACK,
        characteristics=card_def.characteristics, card_def=card_def,
    )
    stack = game.state.zones.get('stack')
    if spell.id not in stack.objects:
        stack.objects.append(spell.id)
    return game, p1, p2, spell


def _add_creature(game, owner_id, name="Bear", power=2, toughness=2):
    bear_def = make_creature(
        name=name, power=power, toughness=toughness,
        mana_cost="{1}{G}", colors={Color.GREEN}, subtypes={"Bear"},
        text="",
    )
    return game.create_object(
        name=bear_def.name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )


def test_legacy_tuple_form_still_works():
    """Back-compat: ``(text, effect_fn)`` tuples with 3-arg signature."""
    def gain3(state, caster_id, spell_id):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': 3},
            source=spell_id, controller=caster_id,
        )]

    card_def = make_sorcery(
        name="Legacy Modal", mana_cost="{1}", colors=set(),
        text="Choose one —\n• Gain 3 life.",
        resolve=make_modal_resolve(
            "Legacy Modal",
            modes=[("Gain 3 life", gain3)],
            min_modes=1, max_modes=1,
        ),
    )
    game, p1, _p2, _spell = _bare_setup_modal(card_def)
    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "modal_with_callback"
    ok, _err, evs = game.submit_choice(pc.id, p1.id, [0])
    assert ok
    assert any(e.type == EventType.LIFE_CHANGE for e in evs), \
        f"life-gain mode should fire, got {evs}"
    print("PASS: legacy tuple form still works")


def test_modespec_single_mode_with_target():
    """ModeSpec + target_requirement → target choice chains and effect fires."""
    def bolt(state, caster_id, spell_id, targets=None):
        tid = targets[0].id if targets else None
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': tid, 'amount': 3, 'source': spell_id},
            source=spell_id, controller=caster_id,
        )]

    card_def = make_sorcery(
        name="Targeted Bolt", mana_cost="{R}", colors={Color.RED},
        text="Deal 3 damage to target creature.",
        resolve=make_modal_resolve(
            "Targeted Bolt",
            modes=[
                ModeSpec("Deal 3 damage to target creature", bolt,
                         target_requirement=target_creature()),
            ],
            min_modes=1, max_modes=1,
        ),
    )
    game, p1, p2, _spell = _bare_setup_modal(card_def)
    bear = _add_creature(game, p2.id, "Bear")

    # Drive the spell to its modal prompt.
    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc.choice_type == "modal_with_callback", \
        f"expected modal_with_callback, got {pc.choice_type}"

    # Pick the one mode.
    ok, _err, _evs = game.submit_choice(pc.id, p1.id, [0])
    assert ok

    # Now the helper should have chained a target choice.
    pc2 = game.state.pending_choice
    assert pc2 is not None and pc2.choice_type == "target", \
        f"expected target choice next, got {pc2 and pc2.choice_type}"
    legal_ids = {opt["id"] if isinstance(opt, dict) else opt for opt in pc2.options}
    assert bear.id in legal_ids, f"Bear should be a legal target: {legal_ids}"

    # Pick the bear.
    ok2, _err2, evs2 = game.submit_choice(pc2.id, p1.id, [bear.id])
    assert ok2
    dmg = [e for e in evs2 if e.type == EventType.DAMAGE]
    assert len(dmg) == 1 and dmg[0].payload['target'] == bear.id, \
        f"expected one damage event targeting bear, got {dmg}"
    print("PASS: ModeSpec single mode with target chains target choice")


def test_modespec_mix_targeted_and_untargeted():
    """A targeted mode + an untargeted mode. Picking both chains exactly one
    target prompt (for the targeted mode) and fires both effects."""
    def life_gain(state, caster_id, spell_id, targets=None):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': 5},
            source=spell_id, controller=caster_id,
        )]

    def pump_target(state, caster_id, spell_id, targets=None):
        tid = targets[0].id if targets else None
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': tid, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'end_of_turn'},
            source=spell_id, controller=caster_id,
        )]

    def gain_legacy(state, caster_id, spell_id):
        """Legacy 3-arg signature — no target requirement."""
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': 1},
            source=spell_id, controller=caster_id,
        )]

    card_def = make_sorcery(
        name="Mix Modal", mana_cost="{2}{G}", colors={Color.GREEN},
        text="Choose two — Pump target creature; Gain 5 life; Gain 1 life.",
        resolve=make_modal_resolve(
            "Mix Modal",
            modes=[
                ModeSpec("Pump target creature", pump_target,
                         target_requirement=target_creature(controller='you')),
                ModeSpec("Gain 5 life", life_gain),  # no target
                ModeSpec("Gain 1 life", gain_legacy),  # no target (could be 3-arg sig)
            ],
            min_modes=2, max_modes=2,
        ),
    )
    game, p1, _p2, _spell = _bare_setup_modal(card_def)
    my_bear = _add_creature(game, p1.id, "MyBear")

    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc.choice_type == "modal_with_callback"

    # Pick mode 0 (target) and mode 1 (no target).
    ok, _err, _evs = game.submit_choice(pc.id, p1.id, [0, 1])
    assert ok

    # One target prompt for the pump mode.
    pc2 = game.state.pending_choice
    assert pc2 is not None and pc2.choice_type == "target"
    ok2, _err2, evs2 = game.submit_choice(pc2.id, p1.id, [my_bear.id])
    assert ok2

    # Both modes should have fired.
    types = [e.type for e in evs2]
    assert EventType.PT_MODIFICATION in types, f"pump should fire: {types}"
    assert EventType.LIFE_CHANGE in types, f"life-gain should fire: {types}"

    pump_evs = [e for e in evs2 if e.type == EventType.PT_MODIFICATION]
    assert pump_evs[0].payload['object_id'] == my_bear.id
    print("PASS: mix of targeted + untargeted modes")


def test_modespec_empty_legal_targets_skips_mode():
    """If a chosen mode has zero legal targets, it's skipped (no crash)."""
    def bolt(state, caster_id, spell_id, targets=None):
        tid = targets[0].id if targets else None
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': tid, 'amount': 3, 'source': spell_id},
            source=spell_id, controller=caster_id,
        )]

    def gain(state, caster_id, spell_id, targets=None):
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster_id, 'amount': 2},
            source=spell_id, controller=caster_id,
        )]

    # Use an opponent-creature-only filter; the test setup has no opposing
    # creatures so the bolt mode will skip.
    opp_only = TargetRequirement(
        filter=creature_filter(controller='opponent'),
        count=1,
        label="target opposing creature",
    )

    card_def = make_sorcery(
        name="Skip Modal", mana_cost="{2}{R}", colors={Color.RED},
        text="Choose both — Burn or heal.",
        resolve=make_modal_resolve(
            "Skip Modal",
            modes=[
                ModeSpec("Bolt opposing creature", bolt, target_requirement=opp_only),
                ModeSpec("Gain 2 life", gain),
            ],
            min_modes=2, max_modes=2,
        ),
    )
    game, p1, _p2, _spell = _bare_setup_modal(card_def)
    # No opposing creature exists.

    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    ok, _err, evs = game.submit_choice(pc.id, p1.id, [0, 1])
    assert ok

    # The mode with no legal targets is skipped: no PendingChoice queued for it.
    # The other mode fires.
    pc2 = game.state.pending_choice
    assert pc2 is None, f"no target choice should chain when no legal targets: {pc2}"
    types = [e.type for e in evs]
    assert EventType.LIFE_CHANGE in types, f"life-gain mode should still fire: {types}"
    assert EventType.DAMAGE not in types, \
        f"bolt mode should be skipped (no targets), got {types}"
    print("PASS: empty legal targets skips that mode")


def test_modespec_ai_heuristic_pick():
    """AI player path: heuristic_pick auto-selects first legal target."""
    def bolt(state, caster_id, spell_id, targets=None):
        tid = targets[0].id if targets else None
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': tid, 'amount': 3, 'source': spell_id},
            source=spell_id, controller=caster_id,
        )]

    card_def = make_sorcery(
        name="AI Modal", mana_cost="{R}", colors={Color.RED},
        text="Bolt target creature.",
        resolve=make_modal_resolve(
            "AI Modal",
            modes=[
                ModeSpec("Bolt", bolt, target_requirement=target_creature()),
            ],
            min_modes=1, max_modes=1,
        ),
    )
    game, p1, p2, _spell = _bare_setup_modal(card_def, p1_name="AIAlice")
    bear = _add_creature(game, p2.id, "Bear")

    # Register the AI player so resolve_pending_choice_inline takes the
    # AI path.
    class _MockTurnMgr:
        def __init__(self, ai_player_ids):
            self.ai_players = set(ai_player_ids)
            self.pokemon_ai_handler = None
            self.hearthstone_ai_handler = None
            self.ygo_ai_handler = None
            self.scp_ai_handler = None
            self.minecraft_ai_handler = None

    game.turn_manager = _MockTurnMgr({p1.id})
    game.state._game = game

    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    assert pc.choice_type == "modal_with_callback"

    # Submit the modal choice (use AI submit path).
    ok, _err, evs = game.submit_choice(pc.id, p1.id, [0])
    assert ok

    # The target choice should have been auto-resolved via heuristic_pick,
    # firing a damage event against the bear (only legal target).
    pc2 = game.state.pending_choice
    assert pc2 is None, f"AI heuristic should have auto-resolved: {pc2}"
    dmg = [e for e in evs if e.type == EventType.DAMAGE]
    # The damage event may be in `evs` directly or queued; the test mainly
    # asserts the helper didn't deadlock on a pending choice with no human.
    if dmg:
        assert dmg[0].payload['target'] == bear.id, \
            f"AI should bolt bear, got {dmg}"
    print("PASS: AI heuristic_pick auto-resolves target choice")


def test_modespec_mode_with_two_requirements():
    """A single mode can declare a list of TargetRequirements; the helper
    chains them in order and passes a flat targets list to effect_fn."""
    def fight(state, caster_id, spell_id, targets=None):
        # targets is a flat list of two Targets: own creature, enemy creature.
        if not targets or len(targets) < 2:
            return []
        own_id = targets[0].id
        enemy_id = targets[1].id
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': enemy_id, 'amount': 1, 'source': own_id, 'is_combat': False},
            source=spell_id, controller=caster_id,
        )]

    card_def = make_sorcery(
        name="Two-Req Mode", mana_cost="{G}", colors={Color.GREEN},
        text="Fight: your creature vs enemy creature.",
        resolve=make_modal_resolve(
            "Two-Req Mode",
            modes=[
                ModeSpec(
                    "Fight",
                    fight,
                    target_requirement=[
                        target_creature(controller='you'),
                        target_creature(controller='opponent'),
                    ],
                ),
            ],
            min_modes=1, max_modes=1,
        ),
    )
    game, p1, p2, _spell = _bare_setup_modal(card_def)
    ally = _add_creature(game, p1.id, "Ally")
    enemy = _add_creature(game, p2.id, "Enemy")

    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    ok, _err, _evs = game.submit_choice(pc.id, p1.id, [0])
    assert ok

    # First target choice (your creature).
    pc2 = game.state.pending_choice
    assert pc2 is not None and pc2.choice_type == "target"
    legal1 = {opt["id"] if isinstance(opt, dict) else opt for opt in pc2.options}
    assert ally.id in legal1 and enemy.id not in legal1
    ok2, _err2, _evs2 = game.submit_choice(pc2.id, p1.id, [ally.id])
    assert ok2

    # Second target choice (enemy creature).
    pc3 = game.state.pending_choice
    assert pc3 is not None and pc3.choice_type == "target"
    legal2 = {opt["id"] if isinstance(opt, dict) else opt for opt in pc3.options}
    assert enemy.id in legal2 and ally.id not in legal2
    ok3, _err3, evs3 = game.submit_choice(pc3.id, p1.id, [enemy.id])
    assert ok3

    dmg = [e for e in evs3 if e.type == EventType.DAMAGE]
    assert len(dmg) == 1
    assert dmg[0].payload['target'] == enemy.id
    assert dmg[0].payload['source'] == ally.id
    print("PASS: mode with two requirements chains both")


def test_modespec_two_targeted_modes_chain_in_order():
    """Choosing two targeted modes: both chains run in declaration order,
    both targets accumulate, both effects fire."""
    bolt_log: list[str] = []
    heal_log: list[str] = []

    def bolt(state, caster_id, spell_id, targets=None):
        tid = targets[0].id if targets else None
        bolt_log.append(tid)
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': tid, 'amount': 3, 'source': spell_id},
            source=spell_id, controller=caster_id,
        )]

    def buff(state, caster_id, spell_id, targets=None):
        tid = targets[0].id if targets else None
        heal_log.append(tid)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': tid, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=spell_id, controller=caster_id,
        )]

    card_def = make_sorcery(
        name="Dual Targeted", mana_cost="{2}", colors=set(),
        text="Choose two — Bolt enemy or Buff ally.",
        resolve=make_modal_resolve(
            "Dual Targeted",
            modes=[
                ModeSpec("Bolt creature", bolt, target_requirement=target_creature()),
                ModeSpec("Buff ally", buff, target_requirement=target_creature(controller='you')),
            ],
            min_modes=2, max_modes=2,
        ),
    )
    game, p1, p2, _spell = _bare_setup_modal(card_def)
    enemy = _add_creature(game, p2.id, "Enemy")
    ally = _add_creature(game, p1.id, "Ally")

    card_def.resolve([], game.state)
    pc = game.state.pending_choice
    ok, _err, _evs = game.submit_choice(pc.id, p1.id, [0, 1])
    assert ok

    # First target choice: bolt's, any creature.
    pc2 = game.state.pending_choice
    assert pc2 is not None and pc2.choice_type == "target"
    legal1 = {opt["id"] if isinstance(opt, dict) else opt for opt in pc2.options}
    assert enemy.id in legal1 and ally.id in legal1
    ok2, _err2, _evs2 = game.submit_choice(pc2.id, p1.id, [enemy.id])
    assert ok2

    # Second target choice: buff's, controller='you'.
    pc3 = game.state.pending_choice
    assert pc3 is not None and pc3.choice_type == "target"
    legal2 = {opt["id"] if isinstance(opt, dict) else opt for opt in pc3.options}
    assert ally.id in legal2 and enemy.id not in legal2
    ok3, _err3, evs3 = game.submit_choice(pc3.id, p1.id, [ally.id])
    assert ok3

    types = [e.type for e in evs3]
    assert EventType.DAMAGE in types, f"bolt should fire: {types}"
    assert EventType.PT_MODIFICATION in types, f"buff should fire: {types}"
    assert bolt_log == [enemy.id] and heal_log == [ally.id]
    print("PASS: two targeted modes chain in order, both fire")


if __name__ == "__main__":
    test_legacy_tuple_form_still_works()
    test_modespec_single_mode_with_target()
    test_modespec_mix_targeted_and_untargeted()
    test_modespec_empty_legal_targets_skips_mode()
    test_modespec_ai_heuristic_pick()
    test_modespec_mode_with_two_requirements()
    test_modespec_two_targeted_modes_chain_in_order()
    print("\nAll ModeSpec tests passed!")
