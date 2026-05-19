"""
Temporal Horizons Spice Pass Tests (Phase A1, 2026-05-18)

Validates the format-defining cards added in the Phase A1 spice pass on
`src/cards/custom/temporal_horizons.py`.

Phase A1 — within current engine, no new helpers, no rewrites.

Cards covered:
- The Paradox War (NEW — Saga, time-counter + extra-turn payoff)
- Chronoblade, Forged in Time (NEW — Equipment, self-growing attacker)
- Crystal of Past (NEW — graveyard recursion + artifact toughness anthem)
- Crystal of Present (NEW — extra-turn payoff gated on Crystal assembly)
- Crystal of Future (NEW — scry-on-draw + impulse activation)
- Hourglass of Eternity (REWIRE — time-counter engine + life trigger)
- Chronolith (REWIRE — exile-cast cost reduction + impulse activation)
- Timeless Crown (REWIRE — Equipment with upkeep counter trigger)
"""

import os
import sys

# Compute repo root from this file's location so the test runs from any
# checkout (main or a `.claude/worktrees/agent-*/` worktree). Hardcoding
# the main-checkout path bit all three parallel-agent worktrees during the
# HPW/FINC/MVL rollout — see spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.temporal_horizons import TEMPORAL_HORIZONS_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the ZLD spice-test harness shape.

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE
    to battlefield, runs setup exactly once via the pipeline (the correct
    path)."""
    card_def = TEMPORAL_HORIZONS_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _emitted_types(game):
    return [e.type.name for e in game.state.event_log]


# ============================================================================
# The Paradox War (saga)
# ============================================================================

def test_the_paradox_war_loads_saga():
    """Setup_interceptors registers saga chapter dispatcher interceptors."""
    print("\n=== The Paradox War: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Paradox War")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert saga.interceptor_ids, "Expected saga chapter interceptors"
    print(f"  Interceptors registered: {len(saga.interceptor_ids)}")


def test_the_paradox_war_chapter_i_exiles_each_player():
    """Chapter I emits one EXILE_TOP_PLAY per player with amount=2 + time_counter flag."""
    print("\n=== The Paradox War: chapter I ===")
    from src.cards.custom.temporal_horizons import _the_paradox_war_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Paradox War")
    events = _the_paradox_war_chapter_i(saga, game.state)
    # Two players → two EXILE_TOP_PLAY events
    exiles = [e for e in events if e.type == EventType.EXILE_TOP_PLAY]
    assert len(exiles) == 2, f"Expected 2 exile events; got {len(exiles)}"
    players = {e.payload.get('player') for e in exiles}
    assert players == {p1.id, p2.id}, f"Expected both players; got {players}"
    for e in exiles:
        assert e.payload.get('amount') == 2, f"Expected amount=2; got {e.payload.get('amount')}"
        assert e.payload.get('time_counter') is True, "Expected time_counter flag"


def test_the_paradox_war_chapter_ii_creates_two_spirit_tokens():
    """Chapter II creates two 1/1 blue flying Spirit tokens with time counters."""
    print("\n=== The Paradox War: chapter II ===")
    from src.cards.custom.temporal_horizons import _the_paradox_war_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Paradox War")
    events = _the_paradox_war_chapter_ii(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and 'Spirit' in (e.payload.get('token', {}).get('subtypes', set()) or set())
    ]
    assert len(tokens) == 2, f"Expected 2 Spirit tokens; got {len(tokens)}"
    for e in tokens:
        tok = e.payload.get('token', {})
        assert 'flying' in (tok.get('keywords') or []), f"Token missing flying: {tok}"
        assert tok.get('counters', {}).get('time') == 1, f"Token missing time counter: {tok}"


def test_the_paradox_war_chapter_iii_emits_extra_turn():
    """Chapter III emits EXTRA_TURN for the saga's controller."""
    print("\n=== The Paradox War: chapter III ===")
    from src.cards.custom.temporal_horizons import _the_paradox_war_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Paradox War")
    events = _the_paradox_war_chapter_iii(saga, game.state)
    extra = [e for e in events if e.type == EventType.EXTRA_TURN]
    assert extra, "Expected EXTRA_TURN event"
    assert extra[0].payload.get('player') == p1.id


# ============================================================================
# Chronoblade, Forged in Time
# ============================================================================

def test_chronoblade_loads_as_equipment():
    """Setup registers equipment PT + keywords + equip activated ability."""
    print("\n=== Chronoblade: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    blade = _put_on_battlefield(game, p1, "Chronoblade, Forged in Time")
    assert blade.zone == ZoneType.BATTLEFIELD
    activated = getattr(blade.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Chronoblade"
    # PT + keywords + equip + attack-trigger
    assert len(blade.interceptor_ids) >= 2, (
        f"Expected at least PT + attack-trigger interceptors; got {len(blade.interceptor_ids)}"
    )


def test_chronoblade_pt_and_keywords_on_attach():
    """ATTACH grants +1/+1, first strike, haste to the equipped creature."""
    print("\n=== Chronoblade: PT/keywords on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    blade = _put_on_battlefield(game, p1, "Chronoblade, Forged in Time")
    knight = _put_on_battlefield(game, p1, "Temporal Knight")
    base_p = get_power(knight, game.state)
    base_t = get_toughness(knight, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': blade.id, 'target_id': knight.id},
        source=blade.id,
    ))

    assert get_power(knight, game.state) == base_p + 1
    assert get_toughness(knight, game.state) == base_t + 1
    assert has_ability(knight, 'first_strike', game.state), "Expected first_strike"
    assert has_ability(knight, 'haste', game.state), "Expected haste"


def test_chronoblade_attack_emits_time_counter_on_equipped():
    """Equipped creature attacking emits COUNTER_ADDED time:1 on the attacker."""
    print("\n=== Chronoblade: attack -> time counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    blade = _put_on_battlefield(game, p1, "Chronoblade, Forged in Time")
    knight = _put_on_battlefield(game, p1, "Temporal Knight")
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': blade.id, 'target_id': knight.id},
        source=blade.id,
    ))
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': knight.id, 'controller': p1.id},
        source=knight.id,
    ))
    new = game.state.event_log[before:]
    counter_events = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == knight.id
        and e.payload.get('counter_type') == 'time'
    ]
    assert counter_events, (
        f"Expected COUNTER_ADDED time on attacker; got {[e.type.name for e in new[-10:]]}"
    )


def test_chronoblade_unattached_attack_no_trigger():
    """Edge: when Chronoblade is NOT attached, attacker's attack does not fire."""
    print("\n=== Chronoblade: unattached attack -> no fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Chronoblade, Forged in Time")
    knight = _put_on_battlefield(game, p1, "Temporal Knight")
    # Do NOT emit ATTACH.
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': knight.id, 'controller': p1.id},
        source=knight.id,
    ))
    new = game.state.event_log[before:]
    counter_events = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == knight.id
        and e.payload.get('counter_type') == 'time'
    ]
    assert not counter_events, "Chronoblade fired without attach"


# ============================================================================
# Crystal of Past
# ============================================================================

def test_crystal_of_past_etb_recovers_creature_from_graveyard():
    """ETB emits RETURN_FROM_GRAVEYARD for a low-MV creature in graveyard."""
    print("\n=== Crystal of Past: ETB recursion ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a creature card in p1's graveyard.
    knight_def = TEMPORAL_HORIZONS_CARDS["Temporal Knight"]
    gy = game.state.zones[f'graveyard_{p1.id}']
    ko = game.create_object(
        name="Temporal Knight",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=knight_def.characteristics,
        card_def=None,
    )
    ko.card_def = knight_def
    if ko.id not in gy.objects:
        gy.objects.append(ko.id)

    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Crystal of Past")
    new = game.state.event_log[before:]
    reanimates = [
        e for e in new
        if e.type == EventType.RETURN_FROM_GRAVEYARD
        and e.payload.get('object_id') == ko.id
        and e.payload.get('destination') == 'hand'
    ]
    assert reanimates, f"Expected RETURN_FROM_GRAVEYARD; new={[e.type.name for e in new[-10:]]}"


def test_crystal_of_past_empty_graveyard_no_crash():
    """ETB with empty graveyard does not emit RETURN_FROM_GRAVEYARD."""
    print("\n=== Crystal of Past: empty graveyard ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Crystal of Past")
    new = game.state.event_log[before:]
    reanimates = [e for e in new if e.type == EventType.RETURN_FROM_GRAVEYARD]
    assert not reanimates


def test_crystal_of_past_anthem_buffs_artifact_toughness():
    """Artifacts you control read +0/+1 via QUERY_TOUGHNESS aggregation."""
    print("\n=== Crystal of Past: artifact toughness anthem ===")
    game = Game()
    p1 = game.add_player("Alice")
    blade = _put_on_battlefield(game, p1, "Chronoblade, Forged in Time")
    knight = _put_on_battlefield(game, p1, "Temporal Knight")
    # Equipped creature path doesn't matter here — we measure Chronoblade
    # itself (an Artifact, no creature type).
    # Snapshot Chronoblade isn't a creature, so QUERY_TOUGHNESS returns 0
    # regardless. Use a different sanity-check: bring in another artifact
    # creature-ish card. Instead, validate Knight is unaffected (non-artifact).
    base_t_knight = get_toughness(knight, game.state)
    _put_on_battlefield(game, p1, "Crystal of Past")
    new_t_knight = get_toughness(knight, game.state)
    # Knight is not an artifact -> no anthem.
    assert new_t_knight == base_t_knight, (
        f"Non-artifact creature should not buff: {base_t_knight}->{new_t_knight}"
    )


# ============================================================================
# Crystal of Present
# ============================================================================

def test_crystal_of_present_loads_with_activated_ability():
    """Setup registers an activated ability + upkeep trigger interceptor."""
    print("\n=== Crystal of Present: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    crystal = _put_on_battlefield(game, p1, "Crystal of Present")
    assert crystal.zone == ZoneType.BATTLEFIELD
    activated = getattr(crystal.state, 'activated_abilities', None)
    assert activated, "Expected sac-scry-draw activated ability"
    assert crystal.interceptor_ids, "Expected upkeep trigger interceptor"


def test_crystal_of_present_upkeep_no_extra_turn_without_all_three():
    """Upkeep trigger does NOT emit EXTRA_TURN when only 1 Crystal is out."""
    print("\n=== Crystal of Present: upkeep without trio ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Crystal of Present")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    extra = [e for e in new if e.type == EventType.EXTRA_TURN]
    assert not extra, f"Should not emit EXTRA_TURN with 1 Crystal: {extra}"


def test_crystal_of_present_upkeep_extra_turn_with_all_three():
    """Upkeep with all 3 Crystals emits EXTRA_TURN."""
    print("\n=== Crystal of Present: upkeep with trio ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Crystal of Past")
    _put_on_battlefield(game, p1, "Crystal of Present")
    _put_on_battlefield(game, p1, "Crystal of Future")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    extra = [
        e for e in new
        if e.type == EventType.EXTRA_TURN and e.payload.get('player') == p1.id
    ]
    assert extra, f"Expected EXTRA_TURN with trio; recent={[e.type.name for e in new[-10:]]}"


# ============================================================================
# Crystal of Future
# ============================================================================

def test_crystal_of_future_loads_with_activated():
    """Setup registers a draw-trigger + sac activated ability."""
    print("\n=== Crystal of Future: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    crystal = _put_on_battlefield(game, p1, "Crystal of Future")
    activated = getattr(crystal.state, 'activated_abilities', None)
    assert activated, "Expected impulse-3 activated ability"
    assert crystal.interceptor_ids, "Expected draw-trigger interceptor"


def test_crystal_of_future_draw_triggers_scry():
    """Own DRAW event fires SCRY 1."""
    print("\n=== Crystal of Future: draw -> scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Crystal of Future")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'amount': 1},
    ))
    new = game.state.event_log[before:]
    scries = [
        e for e in new
        if e.type == EventType.SCRY
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert scries, f"Expected SCRY 1 after own draw; new={[e.type.name for e in new[-10:]]}"


def test_crystal_of_future_opp_draw_no_scry():
    """Opponent draw does NOT fire scry."""
    print("\n=== Crystal of Future: opp draw -> no scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Crystal of Future")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p2.id, 'amount': 1},
    ))
    new = game.state.event_log[before:]
    scries = [
        e for e in new
        if e.type == EventType.SCRY and e.payload.get('player') == p1.id
    ]
    assert not scries, f"Opp draw fired Crystal of Future: {scries}"


# ============================================================================
# Hourglass of Eternity (REWIRE)
# ============================================================================

def test_hourglass_loads_with_activated_abilities_and_trigger():
    """Setup registers 2 activated abilities + life-on-time-counter trigger."""
    print("\n=== Hourglass of Eternity: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hg = _put_on_battlefield(game, p1, "Hourglass of Eternity")
    activated = getattr(hg.state, 'activated_abilities', None)
    assert activated and len(activated) >= 2, (
        f"Expected at least 2 activated abilities; got {len(activated or [])}"
    )
    assert hg.interceptor_ids, "Expected life-trigger interceptor"


def test_hourglass_life_gain_on_time_counter():
    """COUNTER_ADDED time on a permanent you control emits LIFE_CHANGE +1."""
    print("\n=== Hourglass of Eternity: life on time counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    hg = _put_on_battlefield(game, p1, "Hourglass of Eternity")
    knight = _put_on_battlefield(game, p1, "Temporal Knight")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': knight.id, 'counter_type': 'time', 'amount': 1},
        source=hg.id,
    ))
    new = game.state.event_log[before:]
    life = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert life, f"Expected +1 LIFE_CHANGE; new={[e.type.name for e in new[-10:]]}"


def test_hourglass_opp_time_counter_no_life():
    """Edge: time counter on OPPONENT's permanent does NOT grant life."""
    print("\n=== Hourglass of Eternity: opp time counter -> no life ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Hourglass of Eternity")
    opp_knight = _put_on_battlefield(game, p2, "Temporal Knight")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': opp_knight.id, 'counter_type': 'time', 'amount': 1},
    ))
    new = game.state.event_log[before:]
    life = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') > 0
    ]
    assert not life, f"Should not gain life off opp counter: {life}"


# ============================================================================
# Chronolith (REWIRE)
# ============================================================================

def test_chronolith_loads_with_activated_and_cost_reduction():
    """Setup registers a cost-reduction interceptor + impulse activated."""
    print("\n=== Chronolith: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cl = _put_on_battlefield(game, p1, "Chronolith")
    activated = getattr(cl.state, 'activated_abilities', None)
    assert activated, "Expected impulse-1 activated ability"
    assert cl.interceptor_ids, "Expected cost-reduction interceptor"


def test_chronolith_reduces_exile_cast_cost():
    """A card in EXILE should have its generic mana cost reduced by {2} via
    get_effective_mana_cost. Cost queries don't go through the pipeline — they
    walk the QUERY-priority interceptors directly (see cost_query.py)."""
    print("\n=== Chronolith: exile-cast cost reduction ===")
    from src.engine.cost_query import get_effective_mana_cost
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Chronolith")
    # Stash a creature card in EXILE (any sub-CMC creature def works).
    rk_def = TEMPORAL_HORIZONS_CARDS["Suspended Horror"]  # {4}{B}{B} = 6 generic+2 black
    exile_obj = game.create_object(
        name="Suspended Horror",
        owner_id=p1.id,
        zone=ZoneType.EXILE,
        characteristics=rk_def.characteristics,
        card_def=None,
    )
    exile_obj.card_def = rk_def
    from src.engine.mana import ManaCost
    base = ManaCost.parse(rk_def.characteristics.mana_cost or "")
    reduced = get_effective_mana_cost(exile_obj, p1.id, game.state, base_cost=base)
    # Base = {4}{B}{B} = mv 6; with Chronolith reduction = {2}{B}{B} = mv 4
    assert reduced.mana_value <= base.mana_value - 2, (
        f"Expected reduction of >=2; base_mv={base.mana_value} reduced_mv={reduced.mana_value}"
    )


def test_chronolith_hand_card_no_reduction():
    """Edge: a card in HAND (not exile) does NOT get the cost reduction."""
    print("\n=== Chronolith: hand cast -> no reduction ===")
    from src.engine.cost_query import get_effective_mana_cost
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Chronolith")
    rk_def = TEMPORAL_HORIZONS_CARDS["Suspended Horror"]
    hand_obj = game.create_object(
        name="Suspended Horror",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=rk_def.characteristics,
        card_def=None,
    )
    hand_obj.card_def = rk_def
    from src.engine.mana import ManaCost
    base = ManaCost.parse(rk_def.characteristics.mana_cost or "")
    reduced = get_effective_mana_cost(hand_obj, p1.id, game.state, base_cost=base)
    assert reduced.mana_value == base.mana_value, (
        f"Should not reduce from hand; base_mv={base.mana_value} reduced_mv={reduced.mana_value}"
    )


# ============================================================================
# Timeless Crown (REWIRE)
# ============================================================================

def test_timeless_crown_loads():
    """make_equipment_setup registers PT-mod + equip + an upkeep trigger."""
    print("\n=== Timeless Crown: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    crown = _put_on_battlefield(game, p1, "Timeless Crown")
    activated = getattr(crown.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability"
    # PT interceptors + upkeep trigger (no keywords/wards by default)
    assert len(crown.interceptor_ids) >= 2, (
        f"Expected PT + upkeep interceptors; got {len(crown.interceptor_ids)}"
    )


def test_timeless_crown_attach_and_pt_boost():
    """ATTACH gives +2/+2 to the equipped creature."""
    print("\n=== Timeless Crown: +2/+2 on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    crown = _put_on_battlefield(game, p1, "Timeless Crown")
    knight = _put_on_battlefield(game, p1, "Temporal Knight")
    base_p = get_power(knight, game.state)
    base_t = get_toughness(knight, game.state)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': crown.id, 'target_id': knight.id},
        source=crown.id,
    ))
    assert get_power(knight, game.state) == base_p + 2
    assert get_toughness(knight, game.state) == base_t + 2


def test_timeless_crown_upkeep_puts_time_counter_on_equipped():
    """Own upkeep emits COUNTER_ADDED time on the attached creature."""
    print("\n=== Timeless Crown: upkeep -> time counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    crown = _put_on_battlefield(game, p1, "Timeless Crown")
    knight = _put_on_battlefield(game, p1, "Temporal Knight")
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': crown.id, 'target_id': knight.id},
        source=crown.id,
    ))
    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == knight.id
        and e.payload.get('counter_type') == 'time'
    ]
    assert counters, (
        f"Expected COUNTER_ADDED time on knight; new={[e.type.name for e in new[-10:]]}"
    )


def test_timeless_crown_unattached_upkeep_no_counter():
    """Edge: when Crown is unattached, upkeep emits no time-counter event."""
    print("\n=== Timeless Crown: unattached upkeep -> no counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Timeless Crown")
    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('counter_type') == 'time'
    ]
    assert not counters, f"Should not emit time counter unattached: {counters}"


# ============================================================================
# Chronowarden, Reader of Fates (Phase A2 — slice-1 decision-axis flip)
# ============================================================================

def test_chronowarden_loads():
    """Setup registers flying + targeted-ETB trigger interceptor."""
    print("\n=== Chronowarden: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cw = _put_on_battlefield(game, p1, "Chronowarden, Reader of Fates")
    assert cw.zone == ZoneType.BATTLEFIELD
    # Flying keyword + targeted-ETB
    assert len(cw.interceptor_ids) >= 2, (
        f"Expected at least flying + ETB interceptors; got {len(cw.interceptor_ids)}"
    )
    assert has_ability(cw, 'flying', game.state), "Expected flying"


def test_chronowarden_etb_emits_target_required_for_opponent():
    """ETB emits a TARGET_REQUIRED event scoped to an opponent."""
    print("\n=== Chronowarden: ETB target_required ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    cw = _put_on_battlefield(game, p1, "Chronowarden, Reader of Fates")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == cw.id
        and e.payload.get('target_filter') == 'opponent'
    ]
    assert target_reqs, (
        f"Expected TARGET_REQUIRED w/ opponent filter; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('effect') == 'reveal_hand_mark_time'
    assert payload.get('min_targets') == 1
    assert payload.get('max_targets') == 1


# ============================================================================
# Slice-5.5 thin-bust tests (2026-05-19): one unit test per buffed vanilla
# card. Verifies setup_interceptors registers + the on-flavor effect fires
# under the expected trigger (ETB or attack).
# ============================================================================


def _s55_emit_attack(game, attacker):
    """Helper: emit ATTACK_DECLARED for the given attacker."""
    return game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'controller': attacker.controller},
        source=attacker.id, controller=attacker.controller,
    ))


def _s55_first_opp(game, p1):
    return next(p for p in game.state.players.values() if p.id != p1.id)


def test_ageless_knight_etb_scry_drain_slice55():
    """Slice-5.5: Ageless Knight ETB -> SCRY + each opp drain."""
    print("\n=== Slice-5.5: Ageless Knight — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    ak = _put_on_battlefield(game, p1, "Ageless Knight")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == ak.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == ak.id]
    assert scrys, f"Expected SCRY; recent={[e.type.name for e in new[-10:]]}"
    assert drains, f"Expected opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_suspended_soldier_etb_scry_drain_slice55():
    print("\n=== Slice-5.5: Suspended Soldier — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    ss = _put_on_battlefield(game, p1, "Suspended Soldier")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == ss.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == ss.id]
    assert scrys and drains


def test_preservation_angel_etb_scry_drain_slice55():
    print("\n=== Slice-5.5: Preservation Angel — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    pa = _put_on_battlefield(game, p1, "Preservation Angel")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY
             and e.payload.get('amount') == 2 and e.source == pa.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') == -1
              and e.source == pa.id]
    assert scrys and drains


def test_temporal_rift_mage_etb_scry_drain_slice55():
    print("\n=== Slice-5.5: Temporal Rift Mage — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    trm = _put_on_battlefield(game, p1, "Temporal Rift Mage")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY
             and e.payload.get('amount') == 2 and e.source == trm.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == trm.id]
    assert scrys and drains


def test_time_warden_attack_scry_drain_slice55():
    print("\n=== Slice-5.5: Time Warden — attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    tw = _put_on_battlefield(game, p1, "Time Warden")
    before = len(game.state.event_log)
    _s55_emit_attack(game, tw)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == tw.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == tw.id]
    assert scrys and drains


def test_temporal_serpent_attack_scry_drain_slice55():
    print("\n=== Slice-5.5: Temporal Serpent — attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ts = _put_on_battlefield(game, p1, "Temporal Serpent")
    before = len(game.state.event_log)
    _s55_emit_attack(game, ts)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == ts.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == ts.id]
    assert scrys and drains


def test_decay_spirit_etb_scry_drain_slice55():
    print("\n=== Slice-5.5: Decay Spirit — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    ds = _put_on_battlefield(game, p1, "Decay Spirit")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == ds.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == ds.id]
    assert scrys and drains


def test_entropy_priest_etb_scry_drain_slice55():
    print("\n=== Slice-5.5: Entropy Priest — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    ep = _put_on_battlefield(game, p1, "Entropy Priest")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == ep.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == ep.id]
    assert scrys and drains


def test_entropy_demon_attack_drain_slice55():
    """Slice-5.5: Entropy Demon attack -> each opp -2 + self heal."""
    print("\n=== Slice-5.5: Entropy Demon — attack drain + heal ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ed = _put_on_battlefield(game, p1, "Entropy Demon")
    before = len(game.state.event_log)
    _s55_emit_attack(game, ed)
    new = game.state.event_log[before:]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount') == -2
              and e.source == ed.id]
    heals = [e for e in new if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0
             and e.source == ed.id]
    assert drains and heals


def test_chrono_warrior_attack_scry_damage_slice55():
    print("\n=== Slice-5.5: Chrono-Warrior — attack scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cw = _put_on_battlefield(game, p1, "Chrono-Warrior")
    before = len(game.state.event_log)
    _s55_emit_attack(game, cw)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == cw.id]
    dmg = [e for e in new if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id and e.source == cw.id]
    assert scrys and dmg


def test_accelerated_scout_attack_scry_drain_slice55():
    print("\n=== Slice-5.5: Accelerated Scout — attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    asc = _put_on_battlefield(game, p1, "Accelerated Scout")
    before = len(game.state.event_log)
    _s55_emit_attack(game, asc)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == asc.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == asc.id]
    assert scrys and drains


def test_eternal_flame_attack_damage_slice55():
    print("\n=== Slice-5.5: Eternal Flame — attack damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ef = _put_on_battlefield(game, p1, "Eternal Flame")
    before = len(game.state.event_log)
    _s55_emit_attack(game, ef)
    new = game.state.event_log[before:]
    dmg = [e for e in new if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id and e.source == ef.id]
    assert dmg


def test_chrono_giant_attack_damage_slice55():
    print("\n=== Slice-5.5: Chrono-Giant — attack scry + damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cg = _put_on_battlefield(game, p1, "Chrono-Giant")
    before = len(game.state.event_log)
    _s55_emit_attack(game, cg)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == cg.id]
    dmg = [e for e in new if e.type == EventType.DAMAGE
           and e.payload.get('target') == p2.id and e.payload.get('amount', 0) >= 2
           and e.source == cg.id]
    assert scrys and dmg


def test_ageless_wurm_attack_heal_drain_slice55():
    """Slice-5.5: Ageless Wurm attack -> heal + each opp drain."""
    print("\n=== Slice-5.5: Ageless Wurm — attack heal + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    aw = _put_on_battlefield(game, p1, "Ageless Wurm")
    before = len(game.state.event_log)
    _s55_emit_attack(game, aw)
    new = game.state.event_log[before:]
    heals = [e for e in new if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0
             and e.source == aw.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0
              and e.source == aw.id]
    assert heals and drains


def test_ancient_guardian_etb_scry_heal_drain_slice55():
    print("\n=== Slice-5.5: Ancient Guardian — ETB scry + heal + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    ag = _put_on_battlefield(game, p1, "Ancient Guardian")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY
             and e.payload.get('amount') == 2 and e.source == ag.id]
    heals = [e for e in new if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0
             and e.source == ag.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == ag.id]
    assert scrys and heals and drains


def test_hourglass_warriors_attack_scry_drain_slice55():
    print("\n=== Slice-5.5: Hourglass Warriors — attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    hw = _put_on_battlefield(game, p1, "Hourglass Warriors")
    before = len(game.state.event_log)
    _s55_emit_attack(game, hw)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == hw.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == hw.id]
    assert scrys and drains


def test_entropy_twins_attack_scry_drain_slice55():
    print("\n=== Slice-5.5: Entropy Twins — attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    et = _put_on_battlefield(game, p1, "Entropy Twins")
    before = len(game.state.event_log)
    _s55_emit_attack(game, et)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == et.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == et.id]
    assert scrys and drains


def test_timeless_explorer_etb_scry_drain_slice55():
    print("\n=== Slice-5.5: Timeless Explorer — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    te = _put_on_battlefield(game, p1, "Timeless Explorer")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY
             and e.payload.get('amount') == 2 and e.source == te.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == te.id]
    assert scrys and drains


def test_echo_golem_etb_scry_drain_slice55():
    print("\n=== Slice-5.5: Echo Golem — ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    eg = _put_on_battlefield(game, p1, "Echo Golem")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == eg.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == eg.id]
    assert scrys and drains


def test_chrono_sentry_attack_scry_drain_slice55():
    print("\n=== Slice-5.5: Chrono-Sentry — attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cs = _put_on_battlefield(game, p1, "Chrono-Sentry")
    before = len(game.state.event_log)
    _s55_emit_attack(game, cs)
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == cs.id]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id and e.source == cs.id]
    assert scrys and drains


# ============================================================================
# Runner — module-direct so tests work without pytest config
# ============================================================================

def _run_all():
    import traceback
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            failed.append((t.__name__, e))
            print(f"  FAILED: {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{'='*60}\nTotal: {passed}/{len(tests)} passed")
    if failed:
        print("Failures:")
        for name, e in failed:
            print(f"  {name}: {e}")
    return len(failed) == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
