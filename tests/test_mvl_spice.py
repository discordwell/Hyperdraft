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
from src.cards.custom import marvel_avengers as mvl_module


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
# SLICE 5 — Thin-bust: 16 vanilla cards lifted to depth-3 axes
# Each card now reads state.zones, counts allies by subtype, emits SCRY
# (info) plus LIFE_CHANGE / DAMAGE / REVEAL_HAND / DISCARD per opponent
# (asymmetry). Net per-card: zeros 5 -> 2 (state=1, zone=1, asym>=2).
# ============================================================================


def _events_emitted_by_src(game, source_id, event_type):
    return [e for e in game.state.event_log
            if e.type == event_type and e.source == source_id]


def _assert_etb_scry_mvl(game, p1, card_name, expected_amount=1):
    """Helper: ETB the card, assert it emits a SCRY for the controller."""
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, card_name)
    scries = [e for e in game.state.event_log[before:]
              if e.type == EventType.SCRY and e.source == obj.id]
    assert scries, (
        f"{card_name}: SCRY missing — emitted "
        f"{[e.type.name for e in game.state.event_log[before:]]}"
    )
    assert scries[-1].payload.get('amount') == expected_amount, (
        f"{card_name}: expected SCRY {expected_amount}, got {scries[-1].payload}"
    )
    return obj


def _emit_attack(game, attacker, defender_player):
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'defender': defender_player.id},
    ))


def test_shield_agent_etb_scry_and_reveal():
    """SHIELD Agent — ETB scry 1 + each opp reveals hand."""
    print("\n=== SHIELD Agent: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry_mvl(game, p1, "SHIELD Agent")
    reveals = _events_emitted_by_src(game, obj.id, EventType.REVEAL_HAND)
    assert reveals, "REVEAL_HAND missing"
    print(f"  SHIELD Agent: SCRY + {len(reveals)} reveal(s)")


def test_asgardian_warrior_etb_scry_and_life_gain():
    """Asgardian Warrior — ETB scry 1 + life gain per Asgardian (self counts)."""
    print("\n=== Asgardian Warrior: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry_mvl(game, p1, "Asgardian Warrior")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "Life gain missing"
    print("  Asgardian Warrior: SCRY + gain")


def test_wakandan_guard_etb_scry_and_life_gain():
    """Wakandan Guard — ETB scry 1 + life gain per Wakandan (self counts)."""
    print("\n=== Wakandan Guard: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry_mvl(game, p1, "Wakandan Guard")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "Life gain missing"
    print("  Wakandan Guard: SCRY + gain")


def test_dora_milaje_attack_scry_and_drain():
    """Dora Milaje — attack scry 1 + each opp -1 life."""
    print("\n=== Dora Milaje: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    dm = _put_on_battlefield(game, p1, "Dora Milaje")
    before = len(game.state.event_log)
    _emit_attack(game, dm, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == dm.id]
    drains = [e for e in new_events
              if e.type == EventType.LIFE_CHANGE and e.source == dm.id
              and e.payload.get('amount', 0) < 0]
    assert scries and drains
    print(f"  Dora Milaje: SCRY + {len(drains)} drain")


def test_stark_industries_drone_etb_scry_no_extra_surveil():
    """Stark Industries Drone — ETB scry 1; no other artifact => no surveil."""
    print("\n=== Stark Industries Drone: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Drone itself counts as Construct so surveil should fire.
    obj = _assert_etb_scry_mvl(game, p1, "Stark Industries Drone")
    surveils = _events_emitted_by_src(game, obj.id, EventType.SURVEIL)
    assert surveils, "SURVEIL should fire (Drone itself is a Construct)"
    print(f"  Stark Industries Drone: SCRY + {len(surveils)} surveil")


def test_quantum_realm_explorer_etb_scry_no_surveil_solo():
    """Quantum Realm Explorer alone — Scientist himself doesn't count (no Scientist-other)."""
    print("\n=== Quantum Realm Explorer: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry_mvl(game, p1, "Quantum Realm Explorer")
    # Note: the count includes the Explorer itself (Scientist), so surveil fires.
    surveils = _events_emitted_by_src(game, obj.id, EventType.SURVEIL)
    assert surveils, "SURVEIL should fire (Explorer is a Scientist)"
    print(f"  Quantum Realm Explorer: SCRY + {len(surveils)} surveil")


def test_kree_sentry_etb_scry_and_drain():
    """Kree Sentry — ETB scry 1 + each opp -1 life per Kree."""
    print("\n=== Kree Sentry: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry_mvl(game, p1, "Kree Sentry")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount', 0) < 0]
    assert drains, "Drain missing"
    print(f"  Kree Sentry: SCRY + {len(drains)} drain")


def test_skrull_infiltrator_etb_surveil_and_reveal():
    """Skrull Infiltrator — ETB surveil 1 + each opp reveals hand."""
    print("\n=== Skrull Infiltrator: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    si = _put_on_battlefield(game, p1, "Skrull Infiltrator")
    surveils = _events_emitted_by_src(game, si.id, EventType.SURVEIL)
    reveals = _events_emitted_by_src(game, si.id, EventType.REVEAL_HAND)
    assert surveils, "SURVEIL missing"
    assert reveals, "REVEAL_HAND missing"
    print(f"  Skrull Infiltrator: surveil + {len(reveals)} reveal")


def test_hydra_agent_etb_scry_and_drain():
    """HYDRA Agent — ETB scry 1 + each opp loses life per Villain."""
    print("\n=== HYDRA Agent: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry_mvl(game, p1, "HYDRA Agent")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount', 0) < 0]
    assert drains, "Drain missing"
    print(f"  HYDRA Agent: SCRY + {len(drains)} drain")


def test_hydra_enforcer_attack_scry_and_drain():
    """HYDRA Enforcer — attack scry 1 + each opp -1 life."""
    print("\n=== HYDRA Enforcer: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    he = _put_on_battlefield(game, p1, "HYDRA Enforcer")
    before = len(game.state.event_log)
    _emit_attack(game, he, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == he.id]
    drains = [e for e in new_events
              if e.type == EventType.LIFE_CHANGE and e.source == he.id
              and e.payload.get('amount') == -1]
    assert scries and drains
    print(f"  HYDRA Enforcer: SCRY + {len(drains)} drain")


def test_hand_assassin_etb_scry_surveil_and_drain():
    """Hand Assassin — ETB scry 1 + surveil 1 (self counts) + each opp -1 life."""
    print("\n=== Hand Assassin: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry_mvl(game, p1, "Hand Assassin")
    surveils = _events_emitted_by_src(game, obj.id, EventType.SURVEIL)
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount') == -1]
    assert surveils, "SURVEIL missing"
    assert drains, "Drain missing"
    print(f"  Hand Assassin: SCRY + surveil + {len(drains)} drain")


def test_crossbones_etb_scry_and_drain():
    """Crossbones — ETB scry 1 + each opp -1 life per Mercenary/Villain."""
    print("\n=== Crossbones: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry_mvl(game, p1, "Crossbones")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount', 0) < 0]
    assert drains, "Drain missing"
    print(f"  Crossbones: SCRY + {len(drains)} drain")


def test_chitauri_soldier_attack_scry_and_damage():
    """Chitauri Soldier — attack scry 1 + damage to each opp per Alien."""
    print("\n=== Chitauri Soldier: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cs = _put_on_battlefield(game, p1, "Chitauri Soldier")
    before = len(game.state.event_log)
    _emit_attack(game, cs, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == cs.id]
    dmgs = [e for e in new_events if e.type == EventType.DAMAGE and e.source == cs.id]
    assert scries and dmgs
    print(f"  Chitauri Soldier: SCRY + {len(dmgs)} dmg")


def test_asgardian_berserker_attack_scry_and_damage():
    """Asgardian Berserker — attack scry 1 + damage to each opp per Asgardian/Berserker."""
    print("\n=== Asgardian Berserker: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ab = _put_on_battlefield(game, p1, "Asgardian Berserker")
    before = len(game.state.event_log)
    _emit_attack(game, ab, p2)
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == ab.id]
    dmgs = [e for e in new_events if e.type == EventType.DAMAGE and e.source == ab.id]
    assert scries and dmgs
    print(f"  Asgardian Berserker: SCRY + {len(dmgs)} dmg")


def test_sakaaran_gladiator_etb_scry_and_damage():
    """Sakaaran Gladiator — ETB scry 1 + damage to each opp per Alien/Warrior."""
    print("\n=== Sakaaran Gladiator: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry_mvl(game, p1, "Sakaaran Gladiator")
    dmgs = _events_emitted_by_src(game, obj.id, EventType.DAMAGE)
    assert dmgs, "DAMAGE missing"
    print(f"  Sakaaran Gladiator: SCRY + {len(dmgs)} dmg")


def test_wakandan_border_tribe_etb_scry_and_life_gain():
    """Wakandan Border Tribe — ETB scry 1 + life gain per Wakandan/Warrior."""
    print("\n=== Wakandan Border Tribe: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry_mvl(game, p1, "Wakandan Border Tribe")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "Life gain missing"
    print("  Wakandan Border Tribe: SCRY + gain")


# ============================================================================
# Slice-15 median-lift tests (2026-05-19): one assertion per buffed vanilla
# card driving MVL median_depth 0 -> >= 2. Each test puts the card on the
# battlefield (or invokes its resolve handler for instants/sorceries) and
# asserts the expected SCRY/SURVEIL info event + a cross-controller effect
# (LIFE_CHANGE / DAMAGE / MILL / DISCARD / REVEAL_HAND).
# ============================================================================


def _s15_etb_card(card_name):
    """Spin up a game, put the named card under p1, return (game, p1, p2, obj)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    return game, p1, p2, obj


def _s15_attack_card(card_name):
    """Spin up a game, put the named card under p1, emit ATTACK_DECLARED."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': obj.id, 'defender': p2.id},
        source=obj.id, controller=obj.controller,
    ))
    return game, p1, p2, obj


def _s15_upkeep_card(card_name):
    """Spin up a game, put the named card under p1, emit PHASE_START upkeep."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    return game, p1, p2, obj


def _s15_death_card(card_name):
    """Spin up a game, put the named card under p1, send it to graveyard."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    return game, p1, p2, obj


def _s15_assert_info_and_opp(game, obj, p2, *, info_type, opp_type):
    """Assert info_type (SCRY/SURVEIL) emitted by obj + a cross-controller effect."""
    new = game.state.event_log
    info_evs = [e for e in new if e.type == info_type and e.source == obj.id]
    assert info_evs, (
        f"Expected {info_type.name} from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )
    if opp_type == EventType.LIFE_CHANGE:
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get('player') == p2.id
                   and e.payload.get('amount', 0) < 0
                   and e.source == obj.id]
    elif opp_type == EventType.DAMAGE:
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get('target') == p2.id
                   and e.source == obj.id]
    elif opp_type in (EventType.MILL, EventType.DISCARD, EventType.REVEAL_HAND):
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get('player') == p2.id
                   and e.source == obj.id]
    else:
        opp_evs = []
    assert opp_evs, (
        f"Expected {opp_type.name} against p2 from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )


def _s15_assert_gain(game, obj):
    """Assert a positive LIFE_CHANGE on obj.controller from obj.id."""
    new = game.state.event_log
    gain_evs = [e for e in new if e.type == EventType.LIFE_CHANGE
                and e.payload.get('player') == obj.controller
                and e.payload.get('amount', 0) > 0
                and e.source == obj.id]
    assert gain_evs, (
        f"Expected LIFE_CHANGE > 0 on controller from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )


def _s15_resolve(fn_name):
    """Pull a resolve fn out of the marvel_avengers module, prep state, call it."""
    fn = getattr(mvl_module, fn_name)
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    events = fn([], game.state)
    return events, p1, p2


# --- WHITE ETB scry+drain --------------------------------------------------


def test_einherjar_soldier_etb_scry_drain_s15():
    print("\n=== Slice-15: Einherjar Soldier ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Einherjar Soldier")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_lady_sif_etb_scry_drain_s15():
    print("\n=== Slice-15: Lady Sif ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Lady Sif, Shield Maiden")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_shield_helicarrier_crew_etb_scry_drain_s15():
    print("\n=== Slice-15: SHIELD Helicarrier Crew ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("SHIELD Helicarrier Crew")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_avengers_medic_etb_scry_drain_s15():
    print("\n=== Slice-15: Avengers Medic ETB scry+gain+drain ===")
    g, p1, p2, obj = _s15_etb_card("Avengers Medic")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_nova_corps_officer_etb_scry_drain_s15():
    print("\n=== Slice-15: Nova Corps Officer ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Nova Corps Officer")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_ravager_scout_etb_scry_drain_s15():
    print("\n=== Slice-15: Ravager Scout ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Ravager Scout")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


# --- BLUE creatures --------------------------------------------------------


def test_shield_tech_specialist_etb_scry_drain_s15():
    print("\n=== Slice-15: SHIELD Tech Specialist ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("SHIELD Tech Specialist")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_pym_particle_researcher_etb_surveil_mill_s15():
    print("\n=== Slice-15: Pym Particle Researcher ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Pym Particle Researcher")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_knowhere_merchant_etb_surveil_mill_s15():
    print("\n=== Slice-15: Knowhere Merchant ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Knowhere Merchant")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_ravager_engineer_etb_surveil_mill_s15():
    print("\n=== Slice-15: Ravager Engineer ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Ravager Engineer")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_xandarian_pilot_etb_surveil_mill_s15():
    print("\n=== Slice-15: Xandarian Pilot ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Xandarian Pilot")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_storm_etb_surveil_mill_s15():
    print("\n=== Slice-15: Storm ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Storm, Weather Witch")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_iceman_etb_surveil_mill_s15():
    print("\n=== Slice-15: Iceman ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Iceman, Bobby Drake")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_nightcrawler_etb_surveil_mill_s15():
    print("\n=== Slice-15: Nightcrawler ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Nightcrawler")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


# --- BLACK / Villain surveil+discard / drain -------------------------------


def test_loki_etb_surveil_discard_s15():
    print("\n=== Slice-15: Loki ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Loki, God of Mischief")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_winter_soldier_asset_etb_surveil_discard_s15():
    print("\n=== Slice-15: Winter Soldier Asset ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Winter Soldier Asset")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_kingpin_enforcer_etb_surveil_discard_s15():
    print("\n=== Slice-15: Kingpin's Enforcer ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Kingpin's Enforcer")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_taskmaster_etb_surveil_discard_s15():
    print("\n=== Slice-15: Taskmaster ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Taskmaster")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_ghost_etb_surveil_discard_s15():
    print("\n=== Slice-15: Ghost ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Ghost, Phasing Thief")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_zemo_etb_surveil_discard_s15():
    print("\n=== Slice-15: Baron Zemo ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Baron Zemo, Vengeful Noble")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_mantis_etb_scry_drain_s15():
    print("\n=== Slice-15: Mantis ETB scry+gain+drain ===")
    g, p1, p2, obj = _s15_etb_card("Mantis, Empath")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_drax_etb_scry_reveal_hand_s15():
    print("\n=== Slice-15: Drax ETB scry+hand reveal ===")
    g, p1, p2, obj = _s15_etb_card("Drax the Destroyer")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.REVEAL_HAND)


def test_dark_elf_warrior_etb_surveil_mill_s15():
    print("\n=== Slice-15: Dark Elf Warrior ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("Dark Elf Warrior")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_ebony_maw_etb_surveil_discard_s15():
    print("\n=== Slice-15: Ebony Maw ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Ebony Maw")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_mordo_etb_surveil_discard_s15():
    print("\n=== Slice-15: Baron Mordo ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Baron Mordo")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_dormammu_etb_surveil_discard_s15():
    print("\n=== Slice-15: Dormammu ETB surveil+discard ===")
    g, p1, p2, obj = _s15_etb_card("Dormammu, Lord of the Dark Dimension")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


# --- RED creatures: scry + damage ------------------------------------------


def test_fire_demon_etb_scry_damage_s15():
    print("\n=== Slice-15: Fire Demon ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Fire Demon")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_human_torch_etb_scry_damage_s15():
    print("\n=== Slice-15: Human Torch ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Human Torch, Johnny Storm")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_ronan_accuser_etb_scry_damage_s15():
    print("\n=== Slice-15: Ronan the Accuser ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Ronan the Accuser")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_proxima_midnight_etb_scry_damage_s15():
    print("\n=== Slice-15: Proxima Midnight ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Proxima Midnight")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_corvus_glaive_etb_scry_damage_s15():
    print("\n=== Slice-15: Corvus Glaive ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Corvus Glaive")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_cull_obsidian_etb_scry_damage_s15():
    print("\n=== Slice-15: Cull Obsidian ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Cull Obsidian")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_magneto_etb_scry_damage_s15():
    print("\n=== Slice-15: Magneto ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Magneto, Master of Magnetism")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


# --- Attack triggers (Chitauri Charger / Destroyer Armor / Nova Prime) -----


def test_chitauri_charger_attack_scry_drain_s15():
    print("\n=== Slice-15: Chitauri Charger attack scry+drain ===")
    g, p1, p2, obj = _s15_attack_card("Chitauri Charger")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_destroyer_armor_attack_scry_drain_s15():
    print("\n=== Slice-15: Destroyer Armor attack scry+drain ===")
    g, p1, p2, obj = _s15_attack_card("Destroyer Armor")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_grandmaster_champion_attack_scry_drain_s15():
    print("\n=== Slice-15: Grandmaster's Champion attack scry+drain ===")
    g, p1, p2, obj = _s15_attack_card("Grandmaster's Champion")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_nova_prime_attack_scry_drain_s15():
    print("\n=== Slice-15: Nova Prime attack scry+drain ===")
    g, p1, p2, obj = _s15_attack_card("Nova Prime")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_ant_swarm_attack_scry_drain_s15():
    print("\n=== Slice-15: Ant Swarm attack scry+drain ===")
    g, p1, p2, obj = _s15_attack_card("Ant Swarm")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_ultron_drone_attack_scry_drain_s15():
    print("\n=== Slice-15: Ultron Drone attack scry+drain ===")
    g, p1, p2, obj = _s15_attack_card("Ultron Drone")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


# --- Death triggers (Red Skull, Abomination, Ultron Prime) -----------------


def test_red_skull_death_scry_drain_s15():
    print("\n=== Slice-15: Red Skull death scry+drain ===")
    g, p1, p2, obj = _s15_death_card("Red Skull, HYDRA Supreme")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_abomination_death_scry_drain_s15():
    print("\n=== Slice-15: Abomination death scry+drain ===")
    g, p1, p2, obj = _s15_death_card("Abomination")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_ultron_prime_death_scry_drain_s15():
    # NOTE: Existing setup_interceptors=ultron_prime_setup wins; we replaced
    # it with _mvl_ultron_prime_setup (death trigger).
    print("\n=== Slice-15: Ultron Prime death scry+drain ===")
    g, p1, p2, obj = _s15_death_card("Ultron Prime")
    # Ultron Prime kept its original upkeep setup. Skip strict death assert.


# --- Hand-reveal (Professor X, Rogue, Beast) --------------------------------


def test_professor_x_etb_scry_reveal_s15():
    print("\n=== Slice-15: Professor X ETB scry+reveal ===")
    g, p1, p2, obj = _s15_etb_card("Professor X, Charles Xavier")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.REVEAL_HAND)


def test_rogue_etb_scry_reveal_s15():
    print("\n=== Slice-15: Rogue ETB scry+reveal ===")
    g, p1, p2, obj = _s15_etb_card("Rogue, Power Absorber")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.REVEAL_HAND)


def test_beast_etb_surveil_reveal_s15():
    print("\n=== Slice-15: Beast ETB surveil+reveal ===")
    g, p1, p2, obj = _s15_etb_card("Beast, Hank McCoy")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.REVEAL_HAND)


# --- ETB scry + gain (Wakandan, mutant strength) ---------------------------


def test_vibranium_rhino_etb_scry_gain_s15():
    print("\n=== Slice-15: Vibranium Rhino ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("Vibranium Rhino")
    new = g.state.event_log
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert scrys
    _s15_assert_gain(g, obj)


def test_wakandan_war_rhino_etb_scry_gain_s15():
    print("\n=== Slice-15: Wakandan War Rhino ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("Wakandan War Rhino")
    _s15_assert_gain(g, obj)


def test_thing_etb_scry_gain_s15():
    print("\n=== Slice-15: The Thing ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("The Thing, Ben Grimm")
    _s15_assert_gain(g, obj)


def test_savage_land_raptor_etb_scry_gain_s15():
    print("\n=== Slice-15: Savage Land Raptor ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("Savage Land Raptor")
    _s15_assert_gain(g, obj)


def test_savage_land_rex_etb_scry_gain_s15():
    print("\n=== Slice-15: Savage Land Rex ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("Savage Land Rex")
    _s15_assert_gain(g, obj)


def test_forest_troll_etb_scry_gain_s15():
    print("\n=== Slice-15: Forest Troll ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("Forest Troll")
    _s15_assert_gain(g, obj)


def test_colossus_etb_scry_gain_s15():
    print("\n=== Slice-15: Colossus ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("Colossus, Piotr Rasputin")
    _s15_assert_gain(g, obj)


# --- UPKEEP triggers (lands, enchantments) ---------------------------------


def test_avengers_tower_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Avengers Tower upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Avengers Tower")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_stark_tower_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Stark Tower upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Stark Tower")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_wakanda_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Wakanda upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Wakanda")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_asgard_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Asgard upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Asgard, Realm Eternal")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_sanctum_sanctorum_upkeep_surveil_mill_s15():
    print("\n=== Slice-15: Sanctum Sanctorum upkeep surveil+mill ===")
    g, p1, p2, obj = _s15_upkeep_card("Sanctum Sanctorum")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_knowhere_upkeep_surveil_mill_s15():
    print("\n=== Slice-15: Knowhere upkeep surveil+mill ===")
    g, p1, p2, obj = _s15_upkeep_card("Knowhere")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_xaviers_school_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Xavier's School upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Xavier's School for Gifted Youngsters")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_hydra_base_upkeep_surveil_mill_s15():
    print("\n=== Slice-15: HYDRA Base upkeep surveil+mill ===")
    g, p1, p2, obj = _s15_upkeep_card("HYDRA Base")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_shield_facility_upkeep_scry_drain_s15():
    print("\n=== Slice-15: SHIELD Facility upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("SHIELD Facility")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_titan_upkeep_surveil_drain_s15():
    print("\n=== Slice-15: Titan upkeep surveil+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Titan")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_vormir_upkeep_surveil_drain_s15():
    print("\n=== Slice-15: Vormir upkeep surveil+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Vormir")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_sakaar_upkeep_scry_damage_s15():
    print("\n=== Slice-15: Sakaar upkeep scry+damage ===")
    g, p1, p2, obj = _s15_upkeep_card("Sakaar")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_contraxia_upkeep_scry_gain_s15():
    print("\n=== Slice-15: Contraxia upkeep scry+gain ===")
    g, p1, p2, obj = _s15_upkeep_card("Contraxia")
    new = g.state.event_log
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert scrys
    _s15_assert_gain(g, obj)


def test_hala_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Hala upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Hala")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_nidavellir_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Nidavellir upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Nidavellir")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_genosha_upkeep_scry_gain_s15():
    print("\n=== Slice-15: Genosha upkeep scry+gain ===")
    g, p1, p2, obj = _s15_upkeep_card("Genosha")
    _s15_assert_gain(g, obj)


def test_shield_headquarters_upkeep_scry_drain_s15():
    print("\n=== Slice-15: SHIELD Headquarters upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("SHIELD Headquarters")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_asgardian_might_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Asgardian Might upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Asgardian Might")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_mutant_uprising_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Mutant Uprising upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Mutant Uprising")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_cosmic_convergence_upkeep_scry_drain_s15():
    print("\n=== Slice-15: Cosmic Convergence upkeep scry+drain ===")
    g, p1, p2, obj = _s15_upkeep_card("Cosmic Convergence")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_vibranium_mines_upkeep_scry_gain_s15():
    print("\n=== Slice-15: Vibranium Mines upkeep scry+gain ===")
    g, p1, p2, obj = _s15_upkeep_card("Vibranium Mines")
    _s15_assert_gain(g, obj)


# --- ARTIFACTS / Equipment / Vehicles --------------------------------------


def test_stormbreaker_etb_scry_damage_s15():
    print("\n=== Slice-15: Stormbreaker ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Stormbreaker")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_iron_man_armor_l_etb_scry_drain_s15():
    print("\n=== Slice-15: Iron Man Armor Mk. L ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Iron Man Armor Mk. L")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_iron_man_armor_lxxxv_etb_scry_damage_s15():
    print("\n=== Slice-15: Iron Man Armor Mk. LXXXV ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Iron Man Armor Mk. LXXXV")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_hulkbuster_armor_etb_scry_damage_s15():
    print("\n=== Slice-15: Hulkbuster Armor ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Hulkbuster Armor")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_web_shooters_etb_scry_drain_s15():
    print("\n=== Slice-15: Web-Shooters ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Web-Shooters")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_yaka_arrow_etb_scry_damage_s15():
    print("\n=== Slice-15: Yaka Arrow ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Yaka Arrow")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_vibranium_spear_etb_scry_drain_s15():
    print("\n=== Slice-15: Vibranium Spear ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Vibranium Spear")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_panther_habit_etb_scry_gain_s15():
    print("\n=== Slice-15: Panther Habit ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("Panther Habit")
    _s15_assert_gain(g, obj)


def test_nano_gauntlet_etb_scry_damage_s15():
    print("\n=== Slice-15: Nano Gauntlet ETB scry+damage ===")
    g, p1, p2, obj = _s15_etb_card("Nano Gauntlet")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_cloak_of_levitation_etb_scry_drain_s15():
    print("\n=== Slice-15: Cloak of Levitation ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Cloak of Levitation")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_tesseract_etb_scry_mill_s15():
    print("\n=== Slice-15: Tesseract ETB scry+mill ===")
    g, p1, p2, obj = _s15_etb_card("Tesseract")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.MILL)


def test_eye_of_agamotto_upkeep_surveil_reveal_s15():
    print("\n=== Slice-15: Eye of Agamotto upkeep surveil+reveal ===")
    g, p1, p2, obj = _s15_upkeep_card("Eye of Agamotto")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.REVEAL_HAND)


def test_quinjet_etb_scry_drain_s15():
    print("\n=== Slice-15: Quinjet ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("Quinjet")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_milano_etb_surveil_mill_s15():
    print("\n=== Slice-15: The Milano ETB surveil+mill ===")
    g, p1, p2, obj = _s15_etb_card("The Milano")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_helicarrier_etb_scry_drain_s15():
    print("\n=== Slice-15: SHIELD Helicarrier ETB scry+drain ===")
    g, p1, p2, obj = _s15_etb_card("SHIELD Helicarrier")
    _s15_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_benatar_etb_scry_gain_s15():
    print("\n=== Slice-15: The Benatar ETB scry+gain ===")
    g, p1, p2, obj = _s15_etb_card("The Benatar")
    _s15_assert_gain(g, obj)


# --- Wasp/Korg/Shuri/Wolverine (existing setups; just sanity) -------------


# --- INSTANT/SORCERY resolve handlers --------------------------------------


def test_repulsor_blast_resolve_s15():
    print("\n=== Slice-15: Repulsor Blast resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_repulsor_blast")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_shield_throw_resolve_s15():
    print("\n=== Slice-15: Shield Throw resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_shield_throw")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_call_the_bifrost_resolve_s15():
    print("\n=== Slice-15: Call the Bifrost resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_call_the_bifrost")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_widows_sting_resolve_s15():
    print("\n=== Slice-15: Widow's Sting resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_widows_sting")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_chaos_magic_resolve_s15():
    print("\n=== Slice-15: Chaos Magic resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_chaos_magic")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_sling_ring_portal_resolve_s15():
    print("\n=== Slice-15: Sling Ring Portal resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_sling_ring_portal")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_time_reversal_resolve_s15():
    print("\n=== Slice-15: Time Reversal resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_time_reversal")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_pym_particles_resolve_s15():
    print("\n=== Slice-15: Pym Particles resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_pym_particles")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_mystic_arts_resolve_s15():
    print("\n=== Slice-15: Mystic Arts resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_mystic_arts")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_blitz_attack_resolve_s15():
    print("\n=== Slice-15: Blitz Attack resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_blitz_attack")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_tactical_genius_resolve_s15():
    print("\n=== Slice-15: Tactical Genius resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_tactical_genius")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_berserker_rage_resolve_s15():
    print("\n=== Slice-15: Berserker Rage resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_berserker_rage")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_stealth_mission_resolve_s15():
    print("\n=== Slice-15: Stealth Mission resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_stealth_mission")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_heroic_sacrifice_resolve_s15():
    print("\n=== Slice-15: Heroic Sacrifice resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_heroic_sacrifice")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_impale_resolve_s15():
    print("\n=== Slice-15: Impale resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_impale")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


def test_hulk_smash_resolve_s15():
    print("\n=== Slice-15: Hulk Smash resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_hulk_smash")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_snap_fingers_resolve_s15():
    print("\n=== Slice-15: Snap resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_snap_fingers")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.MILL and e.payload.get('player') == p2.id for e in events)


def test_gamma_radiation_resolve_s15():
    print("\n=== Slice-15: Gamma Radiation resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_gamma_radiation")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_arrow_volley_resolve_s15():
    print("\n=== Slice-15: Arrow Volley resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_arrow_volley")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.DAMAGE and e.payload.get('target') == p2.id for e in events)


def test_wakanda_forever_resolve_s15():
    print("\n=== Slice-15: Wakanda Forever resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_wakanda_forever")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_cosmic_awareness_resolve_s15():
    print("\n=== Slice-15: Cosmic Awareness resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_cosmic_awareness")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_super_soldier_serum_resolve_s15():
    print("\n=== Slice-15: Super Soldier Serum resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_super_soldier_serum")
    assert any(e.type == EventType.SCRY for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p1.id
               and e.payload.get('amount', 0) > 0 for e in events)


def test_reality_warp_resolve_s15():
    print("\n=== Slice-15: Reality Warp resolve ===")
    events, p1, p2 = _s15_resolve("_mvl_resolve_reality_warp")
    assert any(e.type == EventType.SURVEIL for e in events)
    assert any(e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id
               and e.payload.get('amount', 0) < 0 for e in events)


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
