"""
Phase 5b — Duskmourn Impending mechanic framework + card wiring.

Reference card text:
    "Impending N—{cost} (If you cast this spell for its impending cost,
     it enters with N time counters and isn't a creature until the last
     is removed. At the beginning of your end step, remove a time counter
     from it.)
     Whenever this permanent enters or attacks, <effect>."

Covered cards:
  - Overlord of the Mistmoors  (5WW / Impending 4 — 2WW)
  - Overlord of the Floodpits  (4UU / Impending 4 — 1UU)
  - Overlord of the Balemurk   (3B  / Impending 5 — 1B)
  - Overlord of the Boilerbilges (5RR / Impending 4 — 2RR)
  - Overlord of the Hauntwoods (3GG / Impending 4 — 1GG)

What we test:
  * `parse_impending_cost` correctly extracts (N, ManaCost) from the rules text.
  * Each Overlord's `setup_interceptors` installs the impending bookkeeping.
  * Casting for the impending cost flags the object pending; on ETB the
    framework installs N time counters and the QUERY_TYPES strip.
  * `get_types(obj, state)` returns a type set with CREATURE stripped while
    counters > 0.
  * End-step decrement reduces the counter by 1 per controller's end step.
  * When the last counter is removed, the strip stops applying — the
    permanent becomes a creature.
  * The enter / attack trigger fires whether cast normally OR for impending.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    PlayerAction, ActionType, ManaCost,
    Characteristics,
    get_types,
)
from src.engine.impending import (
    parse_impending_cost,
    card_has_impending,
    is_impending_castable_from_hand,
    is_impending_pending,
    mark_impending_cast,
    reset_impending_used,
    has_impending_been_used,
)
from src.engine.turn import Phase
from src.engine.mana import ManaType

from src.cards.duskmourn import (
    OVERLORD_OF_THE_MISTMOORS,
    OVERLORD_OF_THE_FLOODPITS,
    OVERLORD_OF_THE_BALEMURK,
    OVERLORD_OF_THE_BOILERBILGES,
    OVERLORD_OF_THE_HAUNTWOODS,
)


_ALL_OVERLORDS = [
    OVERLORD_OF_THE_MISTMOORS,
    OVERLORD_OF_THE_FLOODPITS,
    OVERLORD_OF_THE_BALEMURK,
    OVERLORD_OF_THE_BOILERBILGES,
    OVERLORD_OF_THE_HAUNTWOODS,
]


# =============================================================================
# Helpers
# =============================================================================

def _setup_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.turn_manager.turn_state.active_player_id = p1.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    # Reset the impending-used flag on each card def so tests stay isolated.
    for cd in _ALL_OVERLORDS:
        reset_impending_used(cd)
    return game, p1, p2


def _put_in_hand(game, player, card_def):
    return game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _emit_etb(game, obj, *, payload_extra=None):
    """Emit a ZONE_CHANGE from HAND → BATTLEFIELD for an object."""
    payload = {
        'object_id': obj.id,
        'from_zone_type': ZoneType.HAND,
        'to_zone_type': ZoneType.BATTLEFIELD,
    }
    if payload_extra:
        payload.update(payload_extra)
    game.emit(Event(type=EventType.ZONE_CHANGE, payload=payload))


def _emit_end_step(game, controller_id):
    """Simulate the controller's end step PHASE_START event."""
    game.turn_manager.turn_state.active_player_id = controller_id
    game.state.active_player = controller_id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step'},
        controller=controller_id,
    ))


# =============================================================================
# 1. Text parsing
# =============================================================================

def test_parse_impending_cost_basic():
    """parse_impending_cost extracts (N, ManaCost) from card text."""
    txt = ("Impending 4—{2}{W}{W} (If you cast this spell for its impending "
           "cost, ...) Whenever this permanent enters or attacks, create two "
           "2/1 white Insect creature tokens with flying.")
    parsed = parse_impending_cost(txt)
    assert parsed is not None, "expected a parsed (N, cost) tuple"
    n, cost = parsed
    assert n == 4, f"expected N=4, got {n}"
    assert cost.white == 2, f"expected 2 white in cost, got {cost.white}"
    assert cost.generic == 2, f"expected 2 generic in cost, got {cost.generic}"
    print("PASS test_parse_impending_cost_basic")


def test_parse_impending_cost_variants():
    """Hyphen, en-dash, and em-dash all work; non-impending text returns None."""
    for sep in ["—", "-", "–"]:
        txt = f"Impending 5{sep}{{1}}{{B}} (...) Whenever this permanent enters or attacks, mill four cards."
        parsed = parse_impending_cost(txt)
        assert parsed is not None, f"separator {sep!r} should parse"
        n, _cost = parsed
        assert n == 5, f"separator {sep!r}: expected N=5, got {n}"

    assert parse_impending_cost("no impending here") is None
    assert parse_impending_cost(None) is None
    print("PASS test_parse_impending_cost_variants")


def test_overlord_cards_have_impending():
    """All 5 Overlord card defs advertise impending in their printed text."""
    for cd in _ALL_OVERLORDS:
        assert card_has_impending(cd), f"{cd.name} should report impending=True"
        parsed = parse_impending_cost(cd.text)
        assert parsed is not None, f"{cd.name} text should parse cleanly"
        n, _cost = parsed
        assert n >= 4, f"{cd.name} Impending N should be >= 4, got {n}"
    print("PASS test_overlord_cards_have_impending")


# =============================================================================
# 2. Setup-time installation (no cast yet)
# =============================================================================

def test_normal_cast_etb_no_time_counters():
    """When cast normally (printed cost), enters as creature, no time counters."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)

    # Do NOT mark impending-pending — emit ETB straight.
    _emit_etb(game, obj)

    assert obj.state.counters.get('time', 0) == 0, \
        f"normal cast should have 0 time counters, got {obj.state.counters.get('time', 0)}"
    types = get_types(obj, game.state)
    assert CardType.CREATURE in types, "normal cast: should be a creature"
    print("PASS test_normal_cast_etb_no_time_counters")


def test_impending_cast_etb_installs_time_counters():
    """Cast for impending → enters as non-creature with N time counters."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)

    mark_impending_cast(obj)
    assert is_impending_pending(obj), "should be flagged pending before ETB"

    _emit_etb(game, obj)

    # ETB-installer should have fired COUNTER_ADDED for 4 counters.
    assert obj.state.counters.get('time', 0) == 4, \
        f"impending cast: expected 4 time counters, got {obj.state.counters.get('time', 0)}"
    # Strip kicks in: get_types should NOT include CREATURE.
    types = get_types(obj, game.state)
    assert CardType.CREATURE not in types, \
        f"impending cast: should not be a creature while time counters > 0, got types={types}"
    # Other printed types (enchantment / creature here is an enchantment_creature) remain.
    assert CardType.ENCHANTMENT in types, "enchantment type should remain"
    # Pending flag was consumed.
    assert not is_impending_pending(obj), "pending flag should be cleared after ETB"
    print("PASS test_impending_cast_etb_installs_time_counters")


def test_impending_balemurk_5_counters():
    """Balemurk (Impending 5) installs 5 time counters."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_BALEMURK)

    mark_impending_cast(obj)
    _emit_etb(game, obj)

    assert obj.state.counters.get('time', 0) == 5, \
        f"Balemurk: expected 5 time counters, got {obj.state.counters.get('time', 0)}"
    print("PASS test_impending_balemurk_5_counters")


# =============================================================================
# 3. End step decrement
# =============================================================================

def test_end_step_decrements_time_counter():
    """One end step removes one time counter; not zero immediately."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)
    mark_impending_cast(obj)
    _emit_etb(game, obj)
    assert obj.state.counters.get('time', 0) == 4

    _emit_end_step(game, p1.id)
    assert obj.state.counters.get('time', 0) == 3, \
        f"after 1 end step: expected 3 counters, got {obj.state.counters.get('time', 0)}"
    # Still not a creature.
    types = get_types(obj, game.state)
    assert CardType.CREATURE not in types
    print("PASS test_end_step_decrements_time_counter")


def test_become_creature_after_n_end_steps():
    """After N end steps, the last counter is removed → becomes a creature."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)
    mark_impending_cast(obj)
    _emit_etb(game, obj)
    assert obj.state.counters.get('time', 0) == 4

    for i in range(4):
        _emit_end_step(game, p1.id)
        expected = 4 - (i + 1)
        actual = obj.state.counters.get('time', 0)
        assert actual == expected, \
            f"after {i+1} end steps: expected {expected} counters, got {actual}"

    # Now CREATURE should be back in the effective types.
    types = get_types(obj, game.state)
    assert CardType.CREATURE in types, \
        f"after last counter removed: should be a creature, got types={types}"
    print("PASS test_become_creature_after_n_end_steps")


def test_end_step_not_decrement_after_zero():
    """Once counters are 0, additional end steps do not push counters negative."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)
    mark_impending_cast(obj)
    _emit_etb(game, obj)

    # Burn down to 0.
    for _ in range(4):
        _emit_end_step(game, p1.id)
    assert obj.state.counters.get('time', 0) == 0

    # Extra end steps shouldn't change anything.
    for _ in range(3):
        _emit_end_step(game, p1.id)
    assert obj.state.counters.get('time', 0) == 0
    types = get_types(obj, game.state)
    assert CardType.CREATURE in types
    print("PASS test_end_step_not_decrement_after_zero")


def test_end_step_opponent_does_not_decrement():
    """The opponent's end step does NOT decrement time counters."""
    game, p1, p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)
    mark_impending_cast(obj)
    _emit_etb(game, obj)
    assert obj.state.counters.get('time', 0) == 4

    # End step under p2 (opponent) — should NOT decrement.
    _emit_end_step(game, p2.id)
    assert obj.state.counters.get('time', 0) == 4, \
        "opponent's end step should not decrement controller's time counters"
    print("PASS test_end_step_opponent_does_not_decrement")


# =============================================================================
# 4. ETB / attack trigger fires regardless of impending state
# =============================================================================

def _count_tokens_controlled_by(state, controller_id):
    """Count token objects on the battlefield controlled by the given player."""
    bf = state.zones.get('battlefield')
    if bf is None:
        return 0
    n = 0
    for oid in bf.objects:
        o = state.objects.get(oid)
        if o is None:
            continue
        if o.state.is_token and o.controller == controller_id:
            n += 1
    return n


def test_enter_trigger_fires_when_cast_normally():
    """Hauntwoods normal cast: enter trigger fires (creates an Everywhere token)."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_HAUNTWOODS)
    before = _count_tokens_controlled_by(game.state, p1.id)
    _emit_etb(game, obj)
    after = _count_tokens_controlled_by(game.state, p1.id)

    assert after > before, \
        f"normal cast: enter trigger should create a token (before={before} after={after})"
    print("PASS test_enter_trigger_fires_when_cast_normally")


def test_enter_trigger_fires_when_cast_for_impending():
    """Hauntwoods impending cast: enter trigger also fires (lives on battlefield, not on creature type)."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_HAUNTWOODS)
    mark_impending_cast(obj)
    before = _count_tokens_controlled_by(game.state, p1.id)
    _emit_etb(game, obj)
    after = _count_tokens_controlled_by(game.state, p1.id)

    assert obj.state.counters.get('time', 0) == 4, "impending counters installed"
    assert after > before, \
        f"impending cast: enter trigger should still fire (before={before} after={after})"
    print("PASS test_enter_trigger_fires_when_cast_for_impending")


# =============================================================================
# 5. Cast-from-hand eligibility
# =============================================================================

def test_is_impending_castable_from_hand():
    """The cast surface helper recognises Overlords in hand."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)
    assert is_impending_castable_from_hand(obj, game.state, p1.id), \
        "Mistmoors in hand should be impending-castable"

    # Marking the card def as used should disable it.
    from src.engine.impending import mark_impending_used
    mark_impending_used(OVERLORD_OF_THE_MISTMOORS)
    try:
        assert not is_impending_castable_from_hand(obj, game.state, p1.id), \
            "Mistmoors after use should not be impending-castable"
    finally:
        reset_impending_used(OVERLORD_OF_THE_MISTMOORS)
    print("PASS test_is_impending_castable_from_hand")


# =============================================================================
# 6. Smoke tests — each Overlord wires impending bookkeeping
# =============================================================================

def _smoke_impending_for(card_def, expected_n):
    """Generic smoke: impending cast installs N time counters and strips creature."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, card_def)
    mark_impending_cast(obj)
    _emit_etb(game, obj)
    counters = obj.state.counters.get('time', 0)
    types = get_types(obj, game.state)
    assert counters == expected_n, \
        f"{card_def.name}: expected {expected_n} time counters, got {counters}"
    assert CardType.CREATURE not in types, \
        f"{card_def.name}: should not be a creature while impending"
    return obj


def _count_tokens_on_bf(state, controller_id):
    n = 0
    for o in state.objects.values():
        if o.zone == ZoneType.BATTLEFIELD and o.state.is_token and o.controller == controller_id:
            n += 1
    return n


def test_mistmoors_smoke():
    obj = _smoke_impending_for(OVERLORD_OF_THE_MISTMOORS, 4)
    state = obj._state_ref
    # Mistmoors creates 2 Insect tokens on enter — count any tokens controlled by Mistmoors's controller.
    n = _count_tokens_on_bf(state, obj.controller)
    assert n >= 2, f"Mistmoors: expected >=2 token-permanents from enter trigger, got {n}"
    print("PASS test_mistmoors_smoke")


def test_floodpits_smoke():
    _smoke_impending_for(OVERLORD_OF_THE_FLOODPITS, 4)
    print("PASS test_floodpits_smoke")


def test_balemurk_smoke():
    _smoke_impending_for(OVERLORD_OF_THE_BALEMURK, 5)
    print("PASS test_balemurk_smoke")


def test_boilerbilges_smoke():
    _smoke_impending_for(OVERLORD_OF_THE_BOILERBILGES, 4)
    print("PASS test_boilerbilges_smoke")


def test_hauntwoods_smoke():
    obj = _smoke_impending_for(OVERLORD_OF_THE_HAUNTWOODS, 4)
    state = obj._state_ref
    n = _count_tokens_on_bf(state, obj.controller)
    assert n >= 1, f"Hauntwoods: expected >=1 token-permanent from enter trigger, got {n}"
    print("PASS test_hauntwoods_smoke")


# =============================================================================
# 7. Re-ETB (flicker) does not re-arm impending bookkeeping
# =============================================================================

def test_pending_flag_consumed_after_etb():
    """After ETB consumes the pending flag, a re-ETB (flicker) does not
    re-arm time counters (the alt-cost was already paid once)."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)
    mark_impending_cast(obj)
    _emit_etb(game, obj)
    assert obj.state.counters.get('time', 0) == 4
    assert not is_impending_pending(obj)

    # Simulate "leaves battlefield, comes back" by clearing counters and re-emitting ETB.
    obj.state.counters.clear()
    _emit_etb(game, obj)
    # Pending was cleared, so counters should NOT be re-added.
    assert obj.state.counters.get('time', 0) == 0, \
        "re-ETB without re-marking should not re-add time counters"
    print("PASS test_pending_flag_consumed_after_etb")


# =============================================================================
# 8. End-to-end cast through the priority surface
# =============================================================================

def test_cast_via_priority_full_flow():
    """End-to-end: legal-action surface exposes `hand:impending`; casting via
    that ability_id installs time counters and strips the creature type."""
    import asyncio
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)

    # Mana for impending ({2}{W}{W})
    game.mana_system.produce_mana(p1.id, ManaType.WHITE, 2)
    game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 2)

    # The impending option should appear among the legal actions.
    actions = game.priority_system.get_legal_actions(p1.id)
    impending_actions = [a for a in actions
                         if a.type == ActionType.CAST_SPELL
                         and a.ability_id == "hand:impending"
                         and a.card_id == obj.id]
    assert len(impending_actions) == 1, \
        f"expected exactly 1 hand:impending option, got {len(impending_actions)}"

    # Issue the cast action.
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=obj.id,
        ability_id="hand:impending",
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    assert obj.zone == ZoneType.STACK, f"expected zone STACK after cast, got {obj.zone}"
    # The card def should now be marked impending-used.
    assert has_impending_been_used(OVERLORD_OF_THE_MISTMOORS), \
        "impending-used flag should be set after cast"

    # Resolve via the stack manager + pipeline.
    events = game.stack.resolve_top()
    if game.priority_system and game.priority_system.pipeline:
        for ev in events or []:
            game.priority_system.pipeline.emit(ev)

    assert obj.zone == ZoneType.BATTLEFIELD, \
        f"expected zone BATTLEFIELD after resolution, got {obj.zone}"
    assert obj.state.counters.get('time', 0) == 4, \
        f"expected 4 time counters, got {obj.state.counters.get('time', 0)}"
    types = get_types(obj, game.state)
    assert CardType.CREATURE not in types, \
        f"impending cast should strip CREATURE type; got types={types}"
    print("PASS test_cast_via_priority_full_flow")


def test_priority_surface_no_normal_cast_when_only_impending_affordable():
    """If only the impending cost is affordable (not the printed cost), the
    legal-action surface should still expose the impending option."""
    game, p1, _p2 = _setup_game()
    obj = _put_in_hand(game, p1, OVERLORD_OF_THE_MISTMOORS)

    # Only enough mana for impending {2}{W}{W} (mana value 4), not for {5}{W}{W} (7).
    game.mana_system.produce_mana(p1.id, ManaType.WHITE, 2)
    game.mana_system.produce_mana(p1.id, ManaType.COLORLESS, 2)

    actions = game.priority_system.get_legal_actions(p1.id)
    cast_actions = [a for a in actions
                    if a.type == ActionType.CAST_SPELL and a.card_id == obj.id]
    ability_ids = {a.ability_id for a in cast_actions}
    assert "hand:impending" in ability_ids, \
        f"impending option should be present; got {ability_ids}"
    # Normal cast option (no ability_id) should NOT be present (insufficient mana).
    normal = [a for a in cast_actions if a.ability_id is None]
    assert not normal, \
        f"normal cast option should be absent at low mana; got {normal}"
    print("PASS test_priority_surface_no_normal_cast_when_only_impending_affordable")


# =============================================================================
# Runner
# =============================================================================

def run_all():
    test_parse_impending_cost_basic()
    test_parse_impending_cost_variants()
    test_overlord_cards_have_impending()
    test_normal_cast_etb_no_time_counters()
    test_impending_cast_etb_installs_time_counters()
    test_impending_balemurk_5_counters()
    test_end_step_decrements_time_counter()
    test_become_creature_after_n_end_steps()
    test_end_step_not_decrement_after_zero()
    test_end_step_opponent_does_not_decrement()
    test_enter_trigger_fires_when_cast_normally()
    test_enter_trigger_fires_when_cast_for_impending()
    test_is_impending_castable_from_hand()
    test_mistmoors_smoke()
    test_floodpits_smoke()
    test_balemurk_smoke()
    test_boilerbilges_smoke()
    test_hauntwoods_smoke()
    test_pending_flag_consumed_after_etb()
    test_cast_via_priority_full_flow()
    test_priority_surface_no_normal_cast_when_only_impending_affordable()
    print("\nAll Phase 5b DSK Impending tests passed.")


if __name__ == "__main__":
    run_all()
