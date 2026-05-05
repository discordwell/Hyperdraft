"""
BLB Keywords (Valiant + Expend) framework tests.

Covers the helpers in src/engine/blb_keywords.py and verifies the 10 BLB
cards wired against them in src/cards/bloomburrow.py:

Valiant cards: Mouse Trapper, Whiskervale Forerunner, A-Heartfire Hero,
               Seedglaive Mentor, Veteran Guardmouse.
Expend  cards: Roughshod Duo, Teapot Slinger, Barkknuckle Boxer,
               Brambleguard Veteran, Junkblade Bruiser.

Run with::

    python tests/test_blb_keywords.py
"""

import os
import sys
# Resolve to repo root from this file (works for both regular checkout and worktrees).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, Characteristics, ObjectState, CardDefinition,
    new_id, make_creature,
)
from src.engine.blb_keywords import (
    make_valiant_trigger,
    make_expend_trigger,
)
from src.engine.blb_mechanics import (
    record_mana_spent_for_expend,
    reset_expend_for_turn,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _new_game(p1_name="Alice", p2_name="Bob"):
    game = Game()
    p1 = game.add_player(p1_name)
    p2 = game.add_player(p2_name)
    game.state.active_player = p1.id
    return game, p1.id, p2.id


def _vanilla_creature(game: Game, owner: str, name: str = "Mouse",
                     power: int = 2, toughness: int = 2,
                     subtypes=None) -> GameObject:
    cd = make_creature(
        name=name, power=power, toughness=toughness,
        mana_cost="{1}", colors={Color.WHITE},
        subtypes=set(subtypes) if subtypes else {"Mouse"},
    )
    return game.create_object(name, owner, ZoneType.BATTLEFIELD,
                              cd.characteristics, card_def=cd)


def _emit_target_chosen(game: Game, target_id: str, controller: str,
                        spell_id: str = "spell_x"):
    """Emit one TARGET_CHOSEN event mirroring what stack.py builds."""
    return game.emit(Event(
        type=EventType.TARGET_CHOSEN,
        payload={
            'spell_id': spell_id,
            'target_id': target_id,
            'controller': controller,
        },
        source=spell_id,
        controller=controller,
    ))


# -----------------------------------------------------------------------------
# VALIANT: framework
# -----------------------------------------------------------------------------
def test_valiant_fires_on_first_target_each_turn():
    print("\n=== Valiant: fires once on first target per turn ===")
    game, p1, p2 = _new_game()
    hero = _vanilla_creature(game, p1, name="Hero")

    fire_log = []

    def effect_fn(event, state):
        fire_log.append(event.payload.get('spell_id'))
        return []

    inter = make_valiant_trigger(hero, effect_fn)
    game.register_interceptor(inter, hero)

    _emit_target_chosen(game, hero.id, p1, spell_id="spell_a")
    print(f"  After 1st target: fired={fire_log}")
    assert fire_log == ["spell_a"], fire_log

    _emit_target_chosen(game, hero.id, p1, spell_id="spell_b")
    print(f"  After 2nd target: fired={fire_log}")
    assert fire_log == ["spell_a"], "Valiant must NOT fire twice in one turn"

    # New turn: gate resets when turn_data is cleared.
    game.state.turn_number += 1
    game.state.turn_data.clear()
    _emit_target_chosen(game, hero.id, p1, spell_id="spell_c")
    print(f"  After new-turn target: fired={fire_log}")
    assert fire_log == ["spell_a", "spell_c"], "Valiant must re-fire next turn"
    print("  OK")


def test_valiant_ignores_opponent_spells():
    print("\n=== Valiant: ignores opponent spells/abilities ===")
    game, p1, p2 = _new_game()
    hero = _vanilla_creature(game, p1, name="Hero")

    fire_count = [0]

    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_valiant_trigger(hero, effect_fn), hero)

    # Opponent targets hero → Valiant must NOT fire.
    _emit_target_chosen(game, hero.id, p2, spell_id="opp_spell")
    print(f"  Fire count after opponent target: {fire_count[0]}")
    assert fire_count[0] == 0
    print("  OK")


def test_valiant_uses_target_chosen_event_directly():
    print("\n=== Valiant: filters on TARGET_CHOSEN, not VALIANT_TARGETED ===")
    # This is the headline difference vs. the legacy blb_mechanics helper —
    # this framework reacts to the events the engine ACTUALLY emits.
    game, p1, p2 = _new_game()
    hero = _vanilla_creature(game, p1, name="Hero")

    triggered = []

    def effect_fn(event, state):
        triggered.append(event.type)
        return []

    game.register_interceptor(make_valiant_trigger(hero, effect_fn), hero)

    # VALIANT_TARGETED (legacy event) should NOT fire the new-style trigger:
    game.emit(Event(
        type=EventType.VALIANT_TARGETED,
        payload={'target_id': hero.id, 'controller': p1, 'source_id': 'x'},
        source='x', controller=p1,
    ))
    assert triggered == []

    # But TARGET_CHOSEN (real engine emission) SHOULD fire it:
    _emit_target_chosen(game, hero.id, p1, spell_id="spell_x")
    assert triggered == [EventType.TARGET_CHOSEN]
    print(f"  Triggered events: {[t.name for t in triggered]}")
    print("  OK")


# -----------------------------------------------------------------------------
# EXPEND: framework
# -----------------------------------------------------------------------------
def test_expend_4_fires_when_threshold_crossed():
    print("\n=== Expend 4: trigger fires when crossing 4 mana ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Slinger", power=2, toughness=2,
                       mana_cost="{2}{R}", colors={Color.RED},
                       subtypes={"Otter"})
    obj = game.create_object("Slinger", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    fire_count = [0]

    def effect_fn(event, state):
        fire_count[0] += 1
        return []

    game.register_interceptor(make_expend_trigger(obj, 4, effect_fn), obj)

    # 3-mana spell does NOT cross threshold yet.
    fired = record_mana_spent_for_expend(game.state, p1, 3)
    for ev in fired:
        game.emit(ev)
    print(f"  After 3 mana: fire_count={fire_count[0]}")
    assert fire_count[0] == 0

    # 2-mana spell brings cumulative to 5 → crosses 4 → trigger fires.
    fired = record_mana_spent_for_expend(game.state, p1, 2)
    for ev in fired:
        game.emit(ev)
    print(f"  After cumulative 5: fire_count={fire_count[0]}")
    assert fire_count[0] == 1
    print("  OK")


def test_expend_4_does_not_fire_for_opponent():
    print("\n=== Expend: ignores other-player threshold events ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Slinger", power=2, toughness=2,
                       mana_cost="{2}{R}", colors={Color.RED})
    obj = game.create_object("Slinger", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    fire_count = [0]
    game.register_interceptor(
        make_expend_trigger(obj, 4, lambda e, s: (fire_count.__setitem__(0, fire_count[0]+1) or [])),
        obj,
    )

    # Opponent crosses threshold — our Expend must not fire.
    fired = record_mana_spent_for_expend(game.state, p2, 5)
    for ev in fired:
        game.emit(ev)
    print(f"  Opponent crossed 5 mana, our Expend fire_count={fire_count[0]}")
    assert fire_count[0] == 0
    print("  OK")


def test_expend_x_cost_counts_toward_threshold():
    print("\n=== Expend: X cost contributes (2-mana spell with X=3 → 5 mana) ===")
    # Engine convention (priority.py):
    #   mv_spent = paid_cost.mana_value + action.x_value
    # so a spell printed at {2} with X=3 contributes 5 to the per-turn total.
    # We simulate that by directly invoking record_mana_spent_for_expend with
    # the engine's own arithmetic.
    game, p1, p2 = _new_game()
    cd = make_creature(name="Witness", power=1, toughness=1,
                       mana_cost="{2}", colors=set())
    obj = game.create_object("Witness", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    fire_count = [0]
    game.register_interceptor(
        make_expend_trigger(obj, 4, lambda e, s: (fire_count.__setitem__(0, fire_count[0]+1) or [])),
        obj,
    )

    paid_mv = 2  # printed cost {2}
    x_value = 3  # chosen X
    fired = record_mana_spent_for_expend(game.state, p1, paid_mv + x_value)
    for ev in fired:
        game.emit(ev)
    print(f"  paid_mv+x = {paid_mv + x_value}; fire_count={fire_count[0]}")
    assert fire_count[0] == 1
    print("  OK")


def test_expend_8_threshold():
    print("\n=== Expend 8: only fires once cumulative reaches 8 ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="Boss", power=4, toughness=4,
                       mana_cost="{4}{G}", colors={Color.GREEN})
    obj = game.create_object("Boss", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    fire_count = [0]
    game.register_interceptor(
        make_expend_trigger(obj, 8, lambda e, s: (fire_count.__setitem__(0, fire_count[0]+1) or [])),
        obj,
    )
    for ev in record_mana_spent_for_expend(game.state, p1, 4):
        game.emit(ev)  # cumulative 4 — only EXPEND_4_REACHED fires
    assert fire_count[0] == 0, "Expend 8 must not fire on 4 mana"
    for ev in record_mana_spent_for_expend(game.state, p1, 5):
        game.emit(ev)  # cumulative 9 — EXPEND_8_REACHED now fires
    print(f"  After cumulative 9: fire_count={fire_count[0]}")
    assert fire_count[0] == 1
    print("  OK")


def test_expend_threshold_validation():
    print("\n=== Expend: rejects invalid thresholds ===")
    game, p1, p2 = _new_game()
    cd = make_creature(name="X", power=1, toughness=1,
                       mana_cost="{1}", colors=set())
    obj = game.create_object("X", p1, ZoneType.BATTLEFIELD,
                             cd.characteristics, card_def=cd)
    for bad in (3, 5, 6, 7, 9):
        try:
            make_expend_trigger(obj, bad, lambda e, s: [])
        except ValueError:
            continue
        raise AssertionError(f"Expend N={bad} should be rejected")
    print("  OK")


# -----------------------------------------------------------------------------
# Per-card tests for the 10 wired BLB cards.
# -----------------------------------------------------------------------------
def _put_in_play(game, p_id, card_def):
    return game.create_object(card_def.name, p_id, ZoneType.BATTLEFIELD,
                              card_def.characteristics, card_def=card_def)


# ---- Valiant card tests ----
def _emit_and_collect(game, ev) -> list:
    """Emit an event and return everything the pipeline observed (including
    REACT-injected new_events). pipeline.emit returns the full processed list."""
    return game.emit(ev) or []


def _emit_target_chosen_collect(game, target_id, controller, spell_id="spell_x"):
    return _emit_and_collect(game, Event(
        type=EventType.TARGET_CHOSEN,
        payload={'spell_id': spell_id, 'target_id': target_id,
                 'controller': controller},
        source=spell_id, controller=controller,
    ))


def test_card_mouse_trapper_valiant_taps_opponent_creature():
    print("\n=== Card: Mouse Trapper (Valiant: tap opp creature) ===")
    from src.cards.bloomburrow import MOUSE_TRAPPER
    game, p1, p2 = _new_game()
    mouse = _put_in_play(game, p1, MOUSE_TRAPPER)
    # Provide an opponent creature so the TARGET_REQUIRED has a legal target.
    opp_cd = make_creature(name="Beast", power=2, toughness=2, mana_cost="{2}",
                           colors=set(), subtypes={"Beast"})
    _put_in_play(game, p2, opp_cd)

    events = _emit_target_chosen_collect(game, mouse.id, p1, spell_id="own_spell")
    types_seen = {e.type for e in events}
    print(f"  Types seen: {[t.name for t in types_seen]}")
    # Valiant trigger fires: it injects a TARGET_REQUIRED for "tap opponent creature"
    assert EventType.TARGET_REQUIRED in types_seen
    tr = next(e for e in events if e.type == EventType.TARGET_REQUIRED)
    assert tr.payload.get('effect') == 'tap'
    print("  OK")


def test_card_whiskervale_forerunner_valiant_scry_5():
    print("\n=== Card: Whiskervale Forerunner (Valiant: scry 5) ===")
    from src.cards.bloomburrow import WHISKERVALE_FORERUNNER
    game, p1, p2 = _new_game()
    obj = _put_in_play(game, p1, WHISKERVALE_FORERUNNER)
    events = _emit_target_chosen_collect(game, obj.id, p1, spell_id="spell_w")
    scrys = [e for e in events if e.type == EventType.SCRY]
    print(f"  SCRY events: {len(scrys)}; amounts: {[e.payload.get('amount') for e in scrys]}")
    assert any(e.payload.get('amount') == 5 for e in scrys)
    print("  OK")


def test_card_aheartfire_hero_valiant_counter():
    print("\n=== Card: A-Heartfire Hero (Valiant: +1/+1 counter) ===")
    from src.cards.bloomburrow import AHEARTFIRE_HERO
    game, p1, p2 = _new_game()
    obj = _put_in_play(game, p1, AHEARTFIRE_HERO)
    events = _emit_target_chosen_collect(game, obj.id, p1, spell_id="spell_h")
    counter_evs = [e for e in events
                   if e.type == EventType.COUNTER_ADDED
                   and e.payload.get('object_id') == obj.id]
    print(f"  COUNTER_ADDED events targeting hero: {len(counter_evs)}")
    assert len(counter_evs) == 1
    assert counter_evs[0].payload.get('counter_type') == '+1/+1'
    print("  OK")


def test_card_seedglaive_mentor_valiant_counter():
    print("\n=== Card: Seedglaive Mentor (Valiant: +1/+1 counter) ===")
    from src.cards.bloomburrow import SEEDGLAIVE_MENTOR
    game, p1, p2 = _new_game()
    obj = _put_in_play(game, p1, SEEDGLAIVE_MENTOR)
    events = _emit_target_chosen_collect(game, obj.id, p1, spell_id="spell_s")
    counter_evs = [e for e in events
                   if e.type == EventType.COUNTER_ADDED
                   and e.payload.get('object_id') == obj.id]
    print(f"  COUNTER_ADDED events: {len(counter_evs)}")
    assert len(counter_evs) == 1
    print("  OK")


def test_card_veteran_guardmouse_valiant_pump_first_strike_scry():
    print("\n=== Card: Veteran Guardmouse (Valiant: +1/+0, first strike, scry 1) ===")
    from src.cards.bloomburrow import VETERAN_GUARDMOUSE
    game, p1, p2 = _new_game()
    obj = _put_in_play(game, p1, VETERAN_GUARDMOUSE)
    events = _emit_target_chosen_collect(game, obj.id, p1, spell_id="spell_v")
    types_seen = {e.type for e in events}
    print(f"  Types seen: {[t.name for t in types_seen]}")
    assert EventType.PUMP in types_seen
    assert EventType.GRANT_KEYWORD in types_seen
    assert EventType.SCRY in types_seen
    print("  OK")


# ---- Expend card tests ----
def _trigger_expend_n(game, p_id, n):
    """Push the player past the threshold and emit the resulting events,
    collecting everything the pipeline observes."""
    collected: list = []
    fired = record_mana_spent_for_expend(game.state, p_id, n)
    for ev in fired:
        collected.extend(game.emit(ev) or [])
    return collected


def test_card_roughshod_duo_expend_4_pump_trample():
    print("\n=== Card: Roughshod Duo (Expend 4: target +1/+1 trample) ===")
    from src.cards.bloomburrow import ROUGHSHOD_DUO
    game, p1, p2 = _new_game()
    duo = _put_in_play(game, p1, ROUGHSHOD_DUO)
    events = _trigger_expend_n(game, p1, 4)
    types_seen = {e.type for e in events}
    print(f"  Types seen: {[t.name for t in types_seen]}")
    assert EventType.PUMP in types_seen
    assert EventType.GRANT_KEYWORD in types_seen
    grant_ev = next(e for e in events if e.type == EventType.GRANT_KEYWORD)
    assert grant_ev.payload.get('keyword') == 'trample'
    print("  OK")


def test_card_teapot_slinger_expend_4_damage_each_opponent():
    print("\n=== Card: Teapot Slinger (Expend 4: 2 dmg each opponent) ===")
    from src.cards.bloomburrow import TEAPOT_SLINGER
    game, p1, p2 = _new_game()
    obj = _put_in_play(game, p1, TEAPOT_SLINGER)
    events = _trigger_expend_n(game, p1, 4)
    dmg = [e for e in events if e.type == EventType.DAMAGE]
    print(f"  DAMAGE events: {len(dmg)}; targets: {[e.payload.get('target') for e in dmg]}")
    assert any(e.payload.get('target') == p2 and e.payload.get('amount') == 2 for e in dmg)
    print("  OK")


def test_card_barkknuckle_boxer_expend_4_indestructible():
    print("\n=== Card: Barkknuckle Boxer (Expend 4: indestructible UEOT) ===")
    from src.cards.bloomburrow import BARKKNUCKLE_BOXER
    game, p1, p2 = _new_game()
    obj = _put_in_play(game, p1, BARKKNUCKLE_BOXER)
    events = _trigger_expend_n(game, p1, 4)
    grants = [e for e in events
              if e.type == EventType.GRANT_KEYWORD
              and e.payload.get('object_id') == obj.id]
    print(f"  GRANT_KEYWORD on self: {len(grants)}")
    assert any(e.payload.get('keyword') == 'indestructible' for e in grants)
    print("  OK")


def test_card_brambleguard_veteran_expend_4_raccoon_anthem():
    print("\n=== Card: Brambleguard Veteran (Expend 4: Raccoons +1/+1 vigilance) ===")
    from src.cards.bloomburrow import BRAMBLEGUARD_VETERAN
    game, p1, p2 = _new_game()
    bv = _put_in_play(game, p1, BRAMBLEGUARD_VETERAN)
    raccoon_cd = make_creature(name="Raccoon Pal", power=1, toughness=1,
                               mana_cost="{G}", colors={Color.GREEN},
                               subtypes={"Raccoon"})
    raccoon = _put_in_play(game, p1, raccoon_cd)
    events = _trigger_expend_n(game, p1, 4)
    pumps = [e for e in events
             if e.type == EventType.PUMP
             and e.payload.get('object_id') == raccoon.id]
    grants = [e for e in events
              if e.type == EventType.GRANT_KEYWORD
              and e.payload.get('object_id') == raccoon.id
              and e.payload.get('keyword') == 'vigilance']
    print(f"  Raccoon pumps: {len(pumps)}; vigilance grants: {len(grants)}")
    assert pumps and grants
    print("  OK")


def test_card_junkblade_bruiser_expend_4_self_pump():
    print("\n=== Card: Junkblade Bruiser (Expend 4: +2/+1 UEOT) ===")
    from src.cards.bloomburrow import JUNKBLADE_BRUISER
    game, p1, p2 = _new_game()
    obj = _put_in_play(game, p1, JUNKBLADE_BRUISER)
    events = _trigger_expend_n(game, p1, 4)
    pumps = [e for e in events
             if e.type == EventType.PUMP
             and e.payload.get('object_id') == obj.id]
    print(f"  PUMPs on self: {len(pumps)}")
    assert pumps
    assert pumps[0].payload.get('power') == 2
    assert pumps[0].payload.get('toughness') == 1
    print("  OK")


# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    failures = []
    tests = [
        # Framework
        test_valiant_fires_on_first_target_each_turn,
        test_valiant_ignores_opponent_spells,
        test_valiant_uses_target_chosen_event_directly,
        test_expend_4_fires_when_threshold_crossed,
        test_expend_4_does_not_fire_for_opponent,
        test_expend_x_cost_counts_toward_threshold,
        test_expend_8_threshold,
        test_expend_threshold_validation,
        # Per-card
        test_card_mouse_trapper_valiant_taps_opponent_creature,
        test_card_whiskervale_forerunner_valiant_scry_5,
        test_card_aheartfire_hero_valiant_counter,
        test_card_seedglaive_mentor_valiant_counter,
        test_card_veteran_guardmouse_valiant_pump_first_strike_scry,
        test_card_roughshod_duo_expend_4_pump_trample,
        test_card_teapot_slinger_expend_4_damage_each_opponent,
        test_card_barkknuckle_boxer_expend_4_indestructible,
        test_card_brambleguard_veteran_expend_4_raccoon_anthem,
        test_card_junkblade_bruiser_expend_4_self_pump,
    ]
    for t in tests:
        try:
            t()
        except Exception as exc:
            failures.append((t.__name__, exc))
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED ({len(failures)}/{len(tests)}):")
        for name, exc in failures:
            print(f"  - {name}: {exc}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} BLB KEYWORD TESTS PASSED")
    print("=" * 60)
