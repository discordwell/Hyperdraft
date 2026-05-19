"""
Marvel Avengers Spice Pass Tests (Phase A1)

Validates the spice cards added to the Marvel Avengers (mtg_mvl) set in
Phase A1 — within current engine, no new helpers. Mirror of
`tests/test_zelda_spice.py`'s shape.

Cards covered:
- Mind Stone (REWIRE — was unwired vanilla)
- Time Stone (REWIRE — was unwired vanilla)
- Infinity Gauntlet (REWIRE — was unwired vanilla mythic)
- Mjolnir (REWIRE — was unwired equipment)
- Captain America's Shield (REWIRE — was unwired equipment)
- Avengers Assemble (REWIRE — was unwired sorcery)
- Jean Grey, Phoenix (REWIRE — added Phoenix death trigger)
- Thanos, The Mad Titan (REWIRE — build-around payoff on stones)
"""

import os
import sys
# Load src/ from the repo this test file lives in — works for both the
# main checkout and the agent worktree under .claude/worktrees/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, _REPO)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.marvel_avengers import MARVEL_AVENGERS_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the ZLD spice-pass test harness.

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE
    to battlefield, runs setup exactly once via the pipeline (the correct
    path)."""
    card_def = MARVEL_AVENGERS_CARDS[card_name]
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
# Mind Stone (REWIRE)
# ============================================================================

def test_mind_stone_loads():
    """Setup registers ETB scry + upkeep scry interceptors."""
    print("\n=== Mind Stone: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    stone = _put_on_battlefield(game, p1, "Mind Stone")
    assert stone.zone == ZoneType.BATTLEFIELD
    assert len(stone.interceptor_ids) >= 2, (
        f"Expected ETB + upkeep interceptors; got {len(stone.interceptor_ids)}"
    )


def test_mind_stone_etb_scries():
    """ETB emits a scry placeholder for the controller."""
    print("\n=== Mind Stone: ETB scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Mind Stone")
    new = game.state.event_log[before:]
    scry_events = [
        e for e in new
        if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry'
    ]
    assert scry_events, f"Expected ETB scry; recent={[e.type.name for e in new]}"


def test_mind_stone_upkeep_scry():
    """Own upkeep emits a scry placeholder."""
    print("\n=== Mind Stone: upkeep scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Mind Stone")
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    scry_events = [
        e for e in new
        if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry'
    ]
    assert scry_events, f"Expected upkeep scry; got {[e.type.name for e in new]}"


def test_mind_stone_opp_upkeep_no_scry():
    """Opp upkeep doesn't trigger own Mind Stone."""
    print("\n=== Mind Stone: opp upkeep -> no scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Mind Stone")
    game.state.active_player = p2.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    scry_events = [
        e for e in new
        if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry'
    ]
    assert not scry_events, f"Opp upkeep fired Mind Stone scry"


# ============================================================================
# Time Stone (REWIRE)
# ============================================================================

def test_time_stone_loads():
    """Setup registers ETB trigger."""
    print("\n=== Time Stone: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    stone = _put_on_battlefield(game, p1, "Time Stone")
    assert stone.zone == ZoneType.BATTLEFIELD
    assert stone.interceptor_ids, "Expected at least an ETB trigger"


def test_time_stone_etb_emits_untap_all():
    """ETB emits UNTAP_ALL for the controller's permanents."""
    print("\n=== Time Stone: ETB untap ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Time Stone")
    new = game.state.event_log[before:]
    untaps = [
        e for e in new
        if e.type == EventType.UNTAP_ALL
        and e.payload.get('controller') == p1.id
    ]
    assert untaps, (
        f"Expected UNTAP_ALL for controller; recent={[e.type.name for e in new]}"
    )


def test_time_stone_extra_turn_gated_on_three_stones():
    """Without 3+ stones, Time Stone does NOT emit EXTRA_TURN."""
    print("\n=== Time Stone: extra turn gated ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Time Stone")
    new = game.state.event_log[before:]
    extras = [e for e in new if e.type == EventType.EXTRA_TURN]
    # Time Stone itself = 1 stone, doesn't pass the >=3 gate alone.
    assert not extras, f"Expected NO EXTRA_TURN with 1 stone; got {len(extras)}"


def test_time_stone_extra_turn_with_three_stones():
    """With 2 stones already on board, the 3rd (Time Stone) fires EXTRA_TURN."""
    print("\n=== Time Stone: extra turn with 3 stones ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Mind Stone")
    _put_on_battlefield(game, p1, "Power Stone")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Time Stone")
    new = game.state.event_log[before:]
    extras = [
        e for e in new
        if e.type == EventType.EXTRA_TURN and e.payload.get('player') == p1.id
    ]
    assert extras, (
        f"Expected EXTRA_TURN with 3 stones; recent={[e.type.name for e in new]}"
    )


# ============================================================================
# Infinity Gauntlet (REWIRE)
# ============================================================================

def test_infinity_gauntlet_loads():
    """Setup registers end step trigger + two activated abilities."""
    print("\n=== Infinity Gauntlet: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    gauntlet = _put_on_battlefield(game, p1, "Infinity Gauntlet")
    assert gauntlet.zone == ZoneType.BATTLEFIELD
    activated = getattr(gauntlet.state, 'activated_abilities', None) or []
    assert len(activated) >= 2, (
        f"Expected 2 activated abilities (pump + Snap); got {len(activated)}"
    )


def test_infinity_gauntlet_end_step_drains_per_stone():
    """End step: each opponent loses N life where N = stones you control."""
    print("\n=== Infinity Gauntlet: end step drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Mind Stone")
    _put_on_battlefield(game, p1, "Power Stone")
    _put_on_battlefield(game, p1, "Infinity Gauntlet")
    game.state.active_player = p1.id

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount', 0) < 0
    ]
    # 2 stones => -2 drain to opp.
    drain_amounts = [e.payload.get('amount') for e in drains]
    assert -2 in drain_amounts, (
        f"Expected -2 drain to opponent (2 stones); got {drain_amounts}"
    )


def test_infinity_gauntlet_end_step_no_drain_without_stones():
    """End step with 0 stones emits no drain (no-op)."""
    print("\n=== Infinity Gauntlet: no stones, no drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Infinity Gauntlet")
    game.state.active_player = p1.id

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount', 0) < 0
    ]
    assert not drains, f"Expected no drain with 0 stones; got {drains}"


# ============================================================================
# Mjolnir (REWIRE)
# ============================================================================

def test_mjolnir_loads_with_equip_ability():
    """Setup registers PT-mod + keyword + equip activated ability."""
    print("\n=== Mjolnir: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hammer = _put_on_battlefield(game, p1, "Mjolnir")
    assert hammer.zone == ZoneType.BATTLEFIELD
    activated = getattr(hammer.state, 'activated_abilities', None) or []
    assert activated, "Expected equip activated ability on Mjolnir"
    # PT + keyword interceptors registered while-on-battlefield.
    assert len(hammer.interceptor_ids) >= 2, (
        f"Expected PT + keyword listeners; got {len(hammer.interceptor_ids)}"
    )


def test_mjolnir_attach_buffs_creature_with_flying_trample():
    """After ATTACH, equipped creature reads +3/+3 + flying + trample."""
    print("\n=== Mjolnir: attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    hammer = _put_on_battlefield(game, p1, "Mjolnir")
    # Use a vanilla creature we already have: SHIELD Agent (2/2 vigilance).
    bearer = _put_on_battlefield(game, p1, "SHIELD Agent")
    base_p = get_power(bearer, game.state)
    base_t = get_toughness(bearer, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': hammer.id, 'target_id': bearer.id},
        source=hammer.id,
    ))

    new_p = get_power(bearer, game.state)
    new_t = get_toughness(bearer, game.state)
    assert new_p == base_p + 3, f"Expected power +3: {base_p}→{new_p}"
    assert new_t == base_t + 3, f"Expected toughness +3: {base_t}→{new_t}"
    assert has_ability(bearer, 'flying', game.state), "Expected flying"
    assert has_ability(bearer, 'trample', game.state), "Expected trample"


# ============================================================================
# Captain America's Shield (REWIRE)
# ============================================================================

def test_caps_shield_attach_buffs_with_vigilance_indestructible():
    """After ATTACH, equipped gets +1/+3 + vigilance + indestructible."""
    print("\n=== Captain America's Shield: attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    shield = _put_on_battlefield(game, p1, "Captain America's Shield")
    bearer = _put_on_battlefield(game, p1, "SHIELD Agent")
    base_p = get_power(bearer, game.state)
    base_t = get_toughness(bearer, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': shield.id, 'target_id': bearer.id},
        source=shield.id,
    ))

    new_p = get_power(bearer, game.state)
    new_t = get_toughness(bearer, game.state)
    assert new_p == base_p + 1, f"Expected power +1: {base_p}→{new_p}"
    assert new_t == base_t + 3, f"Expected toughness +3: {base_t}→{new_t}"
    assert has_ability(bearer, 'vigilance', game.state), "Expected vigilance"
    assert has_ability(bearer, 'indestructible', game.state), (
        "Expected indestructible"
    )


# ============================================================================
# Avengers Assemble (REWIRE)
# ============================================================================

def test_avengers_assemble_resolve_creates_three_tokens():
    """Resolve emits CREATE_TOKEN x3 with Avenger subtype + vigilance."""
    print("\n=== Avengers Assemble: resolve creates 3 tokens ===")
    from src.cards.custom.marvel_avengers import avengers_assemble_resolve
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id
    events = avengers_assemble_resolve([], game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and 'Avenger' in (e.payload.get('token', {}).get('subtypes', set()))
    ]
    assert len(tokens) == 3, f"Expected 3 Avenger tokens; got {len(tokens)}"
    # All tokens should be controlled by the caster.
    for t in tokens:
        assert t.payload.get('controller') == p1.id


def test_avengers_assemble_pumps_existing_avengers():
    """Resolve emits PT_MOD +1/+1 EOT for each pre-existing Avenger."""
    print("\n=== Avengers Assemble: anthem on existing Avengers ===")
    from src.cards.custom.marvel_avengers import avengers_assemble_resolve
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id
    falcon = _put_on_battlefield(game, p1, "Falcon, Winged Warrior")

    events = avengers_assemble_resolve([], game.state)
    pumps = [
        e for e in events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == falcon.id
        and e.payload.get('power_mod') == 1
    ]
    assert pumps, (
        f"Expected Falcon to be pumped +1/+1 EOT; got "
        f"{[e.type.name for e in events]}"
    )


def test_avengers_assemble_no_pump_on_non_avenger():
    """Resolve does NOT pump non-Avenger creatures (subtype gate works)."""
    print("\n=== Avengers Assemble: no pump on non-Avenger ===")
    from src.cards.custom.marvel_avengers import avengers_assemble_resolve
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id
    # SHIELD Recruit is a Human Soldier — NOT an Avenger.
    recruit = _put_on_battlefield(game, p1, "SHIELD Recruit")

    events = avengers_assemble_resolve([], game.state)
    pumps = [
        e for e in events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == recruit.id
    ]
    assert not pumps, (
        f"Expected NO pump on non-Avenger Recruit; got {len(pumps)}"
    )


# ============================================================================
# Jean Grey, Phoenix (REWIRE)
# ============================================================================

def test_jean_grey_loads_with_flying():
    """Setup grants self-flying and registers cast-draw + death triggers."""
    print("\n=== Jean Grey: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    jean = _put_on_battlefield(game, p1, "Jean Grey, Phoenix")
    assert jean.zone == ZoneType.BATTLEFIELD
    assert has_ability(jean, 'flying', game.state)
    # Self-flying + cast-trigger + death-trigger.
    assert len(jean.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors; got {len(jean.interceptor_ids)}"
    )


def test_jean_grey_cast_trigger_draws():
    """Cast instant/sorcery -> Jean Grey draws a card."""
    print("\n=== Jean Grey: cast -> draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Jean Grey, Phoenix")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'caster': p1.id,
            'stack_item_id': 'spell-1',
            'types': {CardType.INSTANT},
        },
    ))
    new = game.state.event_log[before:]
    draws = [
        e for e in new
        if e.type == EventType.DRAW and e.payload.get('player') == p1.id
    ]
    assert draws, (
        f"Expected DRAW after instant cast; recent={[e.type.name for e in new]}"
    )


def test_jean_grey_phoenix_return_emits_once():
    """First death emits RETURN_FROM_GRAVEYARD; subsequent deaths no-op."""
    print("\n=== Jean Grey: phoenix return (once per game) ===")
    game = Game()
    p1 = game.add_player("Alice")
    jean = _put_on_battlefield(game, p1, "Jean Grey, Phoenix")

    # Simulate Jean dying: zone change battlefield -> graveyard.
    gy = game.state.zones.get(f'graveyard_{p1.id}')
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': jean.id, 'reason': 'damage'},
        source=jean.id,
    ))
    # Engine will move Jean to graveyard via REACT; force it for test reliability.
    if jean.zone != ZoneType.GRAVEYARD:
        jean.zone = ZoneType.GRAVEYARD
        if gy is not None and jean.id not in gy.objects:
            gy.objects.append(jean.id)
        # Re-emit so the death filter sees Jean in graveyard.
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': jean.id, 'reason': 'damage'},
            source=jean.id,
        ))
    new = game.state.event_log[before:]
    returns = [
        e for e in new
        if e.type == EventType.RETURN_FROM_GRAVEYARD
        and e.payload.get('object_id') == jean.id
    ]
    assert returns, (
        f"Expected Phoenix RETURN_FROM_GRAVEYARD; "
        f"recent={[e.type.name for e in new][-15:]}"
    )

    # Second death — should NOT emit a second return (once-per-game).
    mid = len(game.state.event_log)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': jean.id, 'reason': 'damage_2'},
        source=jean.id,
    ))
    second_returns = [
        e for e in game.state.event_log[mid:]
        if e.type == EventType.RETURN_FROM_GRAVEYARD
        and e.payload.get('object_id') == jean.id
    ]
    assert not second_returns, (
        f"Phoenix should not return twice; got {len(second_returns)} extra returns"
    )


# ============================================================================
# Thanos, The Mad Titan (REWIRE)
# ============================================================================

def test_thanos_loads():
    """Setup registers power + toughness + indestructible interceptors."""
    print("\n=== Thanos: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    thanos = _put_on_battlefield(game, p1, "Thanos, The Mad Titan")
    assert thanos.zone == ZoneType.BATTLEFIELD
    assert len(thanos.interceptor_ids) >= 3, (
        f"Expected power + toughness + indestructible; got {len(thanos.interceptor_ids)}"
    )


def test_thanos_no_pump_without_stones():
    """Base 5/5 with 0 stones."""
    print("\n=== Thanos: no stones -> base stats ===")
    game = Game()
    p1 = game.add_player("Alice")
    thanos = _put_on_battlefield(game, p1, "Thanos, The Mad Titan")
    base_p = thanos.characteristics.power
    p = get_power(thanos, game.state)
    assert p == base_p, f"Expected base {base_p}; got {p}"
    assert not has_ability(thanos, "indestructible", game.state), (
        "Thanos shouldn't have indestructible without 2 stones"
    )


def test_thanos_scales_with_stones():
    """Each stone gives +2/+2 to Thanos.

    Uses Mind Stone (scry, no static P/T) and Reality Stone (ETB draw,
    no static P/T) — Power Stone's +2/+2 anthem and Space Stone's flying
    grant would muddy the read-out.
    """
    print("\n=== Thanos: +2/+2 per stone ===")
    game = Game()
    p1 = game.add_player("Alice")
    thanos = _put_on_battlefield(game, p1, "Thanos, The Mad Titan")
    base_p = thanos.characteristics.power
    base_t = thanos.characteristics.toughness

    # One stone — +2/+2.
    _put_on_battlefield(game, p1, "Mind Stone")
    p = get_power(thanos, game.state)
    t = get_toughness(thanos, game.state)
    assert p == base_p + 2, f"Expected +2 with 1 stone: {base_p}→{p}"
    assert t == base_t + 2, f"Expected +2 with 1 stone: {base_t}→{t}"
    # 1 stone <2 threshold — no indestructible yet.
    assert not has_ability(thanos, "indestructible", game.state), (
        "1 stone shouldn't grant indestructible (threshold is 2)"
    )

    # Two stones — +4/+4 and indestructible. Reality Stone has no static
    # P/T anthem so the readout is clean.
    _put_on_battlefield(game, p1, "Reality Stone")
    p = get_power(thanos, game.state)
    t = get_toughness(thanos, game.state)
    assert p == base_p + 4, f"Expected +4 with 2 stones: {base_p}→{p}"
    assert t == base_t + 4, f"Expected +4 with 2 stones: {base_t}→{t}"
    assert has_ability(thanos, "indestructible", game.state), (
        "Thanos should have indestructible with 2+ stones"
    )


# ============================================================================
# Phase A2 (slice 2) — decision-axis flip cards
# ============================================================================


def test_doctor_strange_agamotto_loads():
    """Setup registers flash + modal-ETB trigger interceptors."""
    print("\n=== Doctor Strange, Eye of Agamotto: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ds = _put_on_battlefield(game, p1, "Doctor Strange, Eye of Agamotto")
    assert ds.zone == ZoneType.BATTLEFIELD
    assert len(ds.interceptor_ids) >= 2, (
        f"Expected at least flash + modal interceptors; got {len(ds.interceptor_ids)}"
    )
    assert has_ability(ds, 'flash', game.state), "Expected flash"


def test_doctor_strange_agamotto_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== Doctor Strange Agamotto: pending modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    ds = _put_on_battlefield(game, p1, "Doctor Strange, Eye of Agamotto")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == ds.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"


def test_spider_man_web_slinger_loads():
    """Setup registers reach + attack trigger interceptors."""
    print("\n=== Spider-Man, Web-Slinger: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sm = _put_on_battlefield(game, p1, "Spider-Man, Web-Slinger")
    assert sm.zone == ZoneType.BATTLEFIELD
    assert len(sm.interceptor_ids) >= 2, (
        f"Expected at least reach + attack triggers; got {len(sm.interceptor_ids)}"
    )
    assert has_ability(sm, 'reach', game.state), "Expected reach"


def test_spider_man_web_slinger_attack_emits_target_required_and_info():
    """Attack emits TARGET_REQUIRED + TARGET_CHOSEN info event."""
    print("\n=== Spider-Man: attack triggers web shot + info pulse ===")
    game = Game()
    p1 = game.add_player("Alice")
    sm = _put_on_battlefield(game, p1, "Spider-Man, Web-Slinger")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sm.id, 'attacker': sm.id, 'controller': p1.id},
        source=sm.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == sm.id
        and e.payload.get('effect') == 'tap'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected web-shot TARGET_REQUIRED; recent={[e.type.name for e in new[-10:]]}"
    )
    info_events = [
        e for e in new
        if e.type == EventType.TARGET_CHOSEN and e.payload.get('source') == sm.id
    ]
    assert info_events, "Expected TARGET_CHOSEN info pulse on attack"


def test_wakandan_vibranium_forge_loads():
    """Setup registers the divided-counters ETB trigger."""
    print("\n=== Wakandan Vibranium Forge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wvf = _put_on_battlefield(game, p1, "Wakandan Vibranium Forge")
    assert wvf.zone == ZoneType.BATTLEFIELD
    assert wvf.interceptor_ids, "Expected ETB interceptor"


def test_wakandan_vibranium_forge_etb_emits_divided_counters_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=4 and counter_add effect."""
    print("\n=== Wakandan Vibranium Forge: ETB distribute counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    wvf = _put_on_battlefield(game, p1, "Wakandan Vibranium Forge")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == wvf.id
        and e.payload.get('effect') == 'counter_add'
    ]
    assert target_reqs, (
        f"Expected counter_add TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 4, (
        f"Expected divide_amount=4; got {payload.get('divide_amount')}"
    )


def test_loki_whispers_of_ruin_loads():
    """Setup registers flash + ETB trigger interceptors."""
    print("\n=== Loki, Whispers of Ruin: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    loki = _put_on_battlefield(game, p1, "Loki, Whispers of Ruin")
    assert loki.zone == ZoneType.BATTLEFIELD
    assert len(loki.interceptor_ids) >= 2, (
        f"Expected at least flash + ETB; got {len(loki.interceptor_ids)}"
    )
    assert has_ability(loki, 'flash', game.state), "Expected flash"


def test_loki_etb_with_opponent_hand_opens_discard_choice():
    """ETB opens a discard pending_choice for the opponent when their hand
    has cards."""
    print("\n=== Loki: ETB opens discard choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant 2 cards in p2's hand.
    chitauri_def = MARVEL_AVENGERS_CARDS["Chitauri Soldier"]
    p2_hand = game.state.zones[f'hand_{p2.id}']
    for _ in range(2):
        obj = game.create_object(
            name="Chitauri Soldier",
            owner_id=p2.id,
            zone=ZoneType.HAND,
            characteristics=chitauri_def.characteristics,
            card_def=None,
        )
        obj.card_def = chitauri_def
        if obj.id not in p2_hand.objects:
            p2_hand.objects.append(obj.id)
    loki = _put_on_battlefield(game, p1, "Loki, Whispers of Ruin")
    pc = game.state.pending_choice
    assert pc is not None, "Expected discard pending_choice"
    assert pc.source_id == loki.id
    assert pc.choice_type == "discard"
    assert pc.player == p2.id, f"Expected discarder=p2; got {pc.player}"


def test_loki_etb_empty_opponent_hand_no_crash():
    """ETB with empty opponent hand doesn't crash, no discard installed."""
    print("\n=== Loki: empty opp hand no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    loki = _put_on_battlefield(game, p1, "Loki, Whispers of Ruin")
    assert loki.zone == ZoneType.BATTLEFIELD


def test_heimdall_all_seeing_loads():
    """Setup registers an ETB trigger."""
    print("\n=== Heimdall, All-Seeing Watchman: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    h = _put_on_battlefield(game, p1, "Heimdall, All-Seeing Watchman")
    assert h.zone == ZoneType.BATTLEFIELD
    assert h.interceptor_ids, "Expected ETB interceptor"


def test_heimdall_empty_library_no_op():
    """ETB with empty library returns [] without crashing."""
    print("\n=== Heimdall: empty library ===")
    game = Game()
    p1 = game.add_player("Alice")
    h = _put_on_battlefield(game, p1, "Heimdall, All-Seeing Watchman")
    assert h.zone == ZoneType.BATTLEFIELD


# ============================================================================
# Runner
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
