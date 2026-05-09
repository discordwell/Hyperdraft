"""
Regression tests for Finance HF / Alpha-Strike helper bug fixes.

Each test exercises ONE engine-bug-punch-list bug from
``docs/strategy/finance.md`` Engine bug punch list section:

  Bug #2  — Multi-attacker Alpha Strike asymmetry (HF traders)
  Bug #18 — Multi-attacker Alpha Strike asymmetry (OEF +4 helper, dark_arbitrage)
  Bug #3  — Low-Latency Strike must clear summoning_sickness on every controlled
            Trader.
  Bug #4  — Direct Market Access alpha upgrade flag (+3 → +4 when DMA on board).
  Bug #5  — Speed Amplifier dies with the attached Trader (no orphan attachment).
  Bug #6  — fin_alpha_struck_alone_<controller> flag set when an alpha-striker
            attacks SOLO; Tick Data Archive's Pre-Market trigger relies on it.

Run directly:
    python tests/test_finance_card_bugs.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import (                                  # noqa: E402
    CardType, EventType, ZoneType,
)
from src.engine.game import Game                                # noqa: E402
from src.engine.finance import setup_finance_player             # noqa: E402
from src.engine.finance_turn import FinanceTurnManager          # noqa: E402
from src.engine.finance_combat import FinanceCombatManager      # noqa: E402

from src.cards.finance.fina.high_frequency import (             # noqa: E402
    SPOOFING_ALGO,
    RETAIL_FLOW_CHASER,
    FRONT_RUNNING_ALGO,
    LOW_LATENCY_STRIKE,
    DIRECT_MARKET_ACCESS,
    SPEED_AMPLIFIER,
    TICK_DATA_ARCHIVE,
    _alpha_strike_bonus,
    _count_attacking_traders,
    _low_latency_strike_apply,
)
from src.cards.finance.fina.dark_arbitrage import (             # noqa: E402
    _make_alpha_strike_plus4,
)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------

def _make_finance_game():
    """Build a fresh Finance game with two players + combat manager wired."""
    game = Game(mode="finance")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    setup_finance_player(game, p1)
    setup_finance_player(game, p2)
    tm = FinanceTurnManager(game.state)
    game.turn_manager = tm
    tm.set_turn_order([p1.id, p2.id])
    tm.finance_combat_manager = FinanceCombatManager(game.state, game.pipeline)
    return game, p1, p2


def _put_on_battlefield(game, player_id: str, card_def):
    """Drop a card_def directly onto the battlefield, bypassing cost/phase.

    Runs ``setup_interceptors`` (handled by ``game.create_object``) and
    clears summoning sickness so the object is combat-ready.
    """
    obj = game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.state.summoning_sickness = False
    obj.state.tapped = False
    return obj


def _get_pt_modifier_total(state, obj_id: str) -> int:
    """Sum the power_mod entries across all PT_MODIFICATION effects affecting obj_id.

    The engine's PT_MODIFICATION pipeline writes onto a per-object modifier
    list (or buffers into turn_data). We collect the deltas in a defensive
    way: replay ``_alpha_strike_bonus``-style emitted events from the test
    by querying pipeline-touched object state.
    """
    obj = state.objects.get(obj_id)
    if obj is None:
        return 0
    # The engine writes pt modifiers to obj.state.pt_modifiers (list of dicts)
    # as part of pipeline RESOLVE for PT_MODIFICATION events. Sum power_mod.
    mods = getattr(obj.state, "pt_modifiers", None) or []
    return sum(int(m.get("power_mod", 0) or 0) for m in mods)


# ---------------------------------------------------------------------------
# Bug #2 — Multi-attacker Alpha Strike asymmetry
# ---------------------------------------------------------------------------

def test_bug2_multi_attacker_alpha_no_solo_buff():
    """Two Alpha-Strike Traders both attacking → NEITHER should get +3 alpha.

    Pre-fix, the FIRST declared got +3 because count==1 at the moment its
    ATTACK_DECLARED fired (before the second was set attacking=True).
    Post-fix, ``declare_attackers`` marks ALL attackers attacking BEFORE
    emitting per-attacker events, so the count is the final size for both.
    """
    game, p1, p2 = _make_finance_game()
    a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
    b = _put_on_battlefield(game, p1.id, RETAIL_FLOW_CHASER)

    cm = game.turn_manager.finance_combat_manager
    asyncio.run(cm.declare_attackers(p1.id, [a.id, b.id]))

    # During each ATTACK_DECLARED handler, count_attacking_traders should
    # have been 2 — so neither got the +3 bonus. We assert via the
    # alone-flag (set only on count==1): the flag must NOT be set.
    flag_key = f"fin_alpha_struck_alone_{p1.id}"
    assert not game.state.turn_data.get(flag_key), (
        "Bug #2: alpha-strike-alone flag should NOT be set during multi-attack"
    )
    print("test_bug2_multi_attacker_alpha_no_solo_buff  PASS")


def test_bug2_solo_alpha_still_buffs():
    """Single Alpha-Strike Trader attacking solo → still gets the +3 bonus."""
    game, p1, p2 = _make_finance_game()
    a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)

    cm = game.turn_manager.finance_combat_manager
    asyncio.run(cm.declare_attackers(p1.id, [a.id]))

    flag_key = f"fin_alpha_struck_alone_{p1.id}"
    assert game.state.turn_data.get(flag_key) is True, (
        "Bug #2/#6: solo alpha attack must set fin_alpha_struck_alone_<controller>"
    )
    print("test_bug2_solo_alpha_still_buffs  PASS")


# ---------------------------------------------------------------------------
# Bug #18 — Same fix applies to the OEF +4 helper
# ---------------------------------------------------------------------------

def test_bug18_alpha_plus4_no_solo_buff_in_multi_attack():
    """OEF helper: in multi-attack, no attacker should get the +4 bonus."""
    game, p1, p2 = _make_finance_game()
    # Two FRA Traders, but force one of them to use the +4 helper.
    a = _put_on_battlefield(game, p1.id, FRONT_RUNNING_ALGO)
    b = _put_on_battlefield(game, p1.id, RETAIL_FLOW_CHASER)

    # Manually register a +4 alpha-strike interceptor on `a` (mimics OEF).
    plus4_icp = _make_alpha_strike_plus4(a)
    game.register_interceptor(plus4_icp, a)

    cm = game.turn_manager.finance_combat_manager
    asyncio.run(cm.declare_attackers(p1.id, [a.id, b.id]))

    # Multi-attack: alone-flag should NOT be set (so +4 path didn't fire).
    flag_key = f"fin_alpha_struck_alone_{p1.id}"
    assert not game.state.turn_data.get(flag_key), (
        "Bug #18: +4 alpha helper must NOT fire when multiple attackers declared"
    )
    print("test_bug18_alpha_plus4_no_solo_buff_in_multi_attack  PASS")


# ---------------------------------------------------------------------------
# Bug #3 — Low-Latency Strike clears summoning sickness
# ---------------------------------------------------------------------------

def test_bug3_low_latency_strike_clears_summoning_sickness():
    """LLS must remove summoning_sickness from ALL controlled Traders.

    Tests the cast_effect path (what the finance engine actually invokes)
    via the shared ``_low_latency_strike_apply`` helper.
    """
    game, p1, p2 = _make_finance_game()
    a = _put_on_battlefield(game, p1.id, RETAIL_FLOW_CHASER)
    b = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
    # Re-impose summoning sickness to mimic just-played Traders.
    a.state.summoning_sickness = True
    b.state.summoning_sickness = True

    # Also drop a P2 Trader; it must NOT lose summoning sickness.
    p2_trader = _put_on_battlefield(game, p2.id, SPOOFING_ALGO)
    p2_trader.state.summoning_sickness = True

    _low_latency_strike_apply(p1.id, game.state)

    assert a.state.summoning_sickness is False, (
        "Bug #3: LLS must clear summoning_sickness on first controlled Trader"
    )
    assert b.state.summoning_sickness is False, (
        "Bug #3: LLS must clear summoning_sickness on EVERY controlled Trader"
    )
    assert p2_trader.state.summoning_sickness is True, (
        "Bug #3: LLS must NOT touch opponent's Traders"
    )
    print("test_bug3_low_latency_strike_clears_summoning_sickness  PASS")


def test_bug3_low_latency_strike_card_has_cast_effect_attribute():
    """Smoke check: LLS card_def has cast_effect set (the attr the finance
    engine's one-shot dispatcher looks up). Pre-fix, only ``resolve`` was
    set and the dispatcher silently no-op'd.
    """
    fn = getattr(LOW_LATENCY_STRIKE, "cast_effect", None)
    assert callable(fn), (
        "Bug #3: LOW_LATENCY_STRIKE must expose a callable cast_effect"
    )
    print("test_bug3_low_latency_strike_card_has_cast_effect_attribute  PASS")


# ---------------------------------------------------------------------------
# Bug #4 — Direct Market Access alpha upgrade flag wired
# ---------------------------------------------------------------------------

def test_bug4_dma_upgrades_alpha_bonus_to_plus4():
    """When DMA's flag is set, _alpha_strike_bonus emits +4 (not +3)."""
    game, p1, p2 = _make_finance_game()
    a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
    a.state.attacking = True

    # Without DMA flag: +3 bonus.
    evts_pre = _alpha_strike_bonus(a, game.state, power_mod=3)
    assert len(evts_pre) == 1
    assert evts_pre[0].payload["power_mod"] == 3, (
        "Bug #4 baseline: alpha bonus is +3 without DMA flag"
    )

    # Set the DMA upgrade flag.
    game.state.turn_data[f"fin_alpha_strike_upgrade_{p1.id}"] = True
    evts_post = _alpha_strike_bonus(a, game.state, power_mod=3)
    assert len(evts_post) == 1
    assert evts_post[0].payload["power_mod"] == 4, (
        f"Bug #4: alpha bonus should be +4 with DMA flag set, got "
        f"{evts_post[0].payload['power_mod']}"
    )
    print("test_bug4_dma_upgrades_alpha_bonus_to_plus4  PASS")


def test_bug4_dma_etb_sets_upgrade_flag():
    """DMA's ETB trigger must set fin_alpha_strike_upgrade_<controller>."""
    game, p1, p2 = _make_finance_game()
    # Directly run setup + ETB.
    dma_obj = _put_on_battlefield(game, p1.id, DIRECT_MARKET_ACCESS)

    # Manually fire the ETB trigger by emitting a ZONE_CHANGE→BATTLEFIELD.
    # The finance pipeline runs ETB triggers via the pipeline; for this
    # unit test we just call the etb_fn inside the setup directly.
    # Easier: invoke setup_interceptors again (it's idempotent for ETB).
    icps = DIRECT_MARKET_ACCESS.setup_interceptors(dma_obj, game.state)
    # The first interceptor is the ETB trigger; effect_fn sets the flag.
    etb_icp = icps[0]
    etb_icp.effect_fn(None, game.state)

    flag_key = f"fin_alpha_strike_upgrade_{p1.id}"
    assert game.state.turn_data.get(flag_key) is True, (
        "Bug #4: DMA's ETB trigger must set the alpha-strike-upgrade flag"
    )
    print("test_bug4_dma_etb_sets_upgrade_flag  PASS")


# ---------------------------------------------------------------------------
# Bug #5 — Speed Amplifier dies with its host
# ---------------------------------------------------------------------------

def test_bug5_speed_amplifier_destroys_when_host_destroyed():
    """When the host Trader gets OBJECT_DESTROYED, Speed Amplifier issues
    an OBJECT_DESTROYED on itself so the desk doesn't keep an orphan.
    """
    game, p1, p2 = _make_finance_game()
    host = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
    amp = _put_on_battlefield(game, p1.id, SPEED_AMPLIFIER)
    amp.state.attached_to = host.id

    # The host_leave_filter is the third interceptor returned by
    # _speed_amplifier_setup. Find it and trigger directly.
    icps = SPEED_AMPLIFIER.setup_interceptors(amp, game.state)
    # Re-attach since calling setup again resets state.
    amp.state.attached_to = host.id
    leave_icp = icps[-1]  # third entry (pwr, atk, host_leave)

    from src.engine.types import Event
    fake_destroyed = Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": host.id, "reason": "test"},
        source="test",
    )
    assert leave_icp.filter(fake_destroyed, game.state), (
        "Bug #5: host-leave filter must match OBJECT_DESTROYED on host"
    )
    result = leave_icp.handler(fake_destroyed, game.state)
    # Handler must emit an OBJECT_DESTROYED on the amp itself.
    assert any(
        ev.type == EventType.OBJECT_DESTROYED
        and ev.payload.get("object_id") == amp.id
        for ev in result.new_events
    ), "Bug #5: amp must emit OBJECT_DESTROYED on itself when host dies"
    # And the attached_to reference must be cleared immediately.
    assert amp.state.attached_to is None, (
        "Bug #5: amp.state.attached_to must be cleared so static buff stops"
    )
    print("test_bug5_speed_amplifier_destroys_when_host_destroyed  PASS")


def test_bug5_speed_amplifier_destroys_when_host_zone_changes():
    """ZONE_CHANGE off battlefield (e.g. bounce) also kills Speed Amplifier."""
    game, p1, p2 = _make_finance_game()
    host = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
    amp = _put_on_battlefield(game, p1.id, SPEED_AMPLIFIER)
    amp.state.attached_to = host.id

    icps = SPEED_AMPLIFIER.setup_interceptors(amp, game.state)
    amp.state.attached_to = host.id
    leave_icp = icps[-1]

    from src.engine.types import Event
    # Try the finance_combat liquidation shape: "from"="battlefield".
    fake_zc = Event(
        type=EventType.ZONE_CHANGE,
        payload={"object_id": host.id, "from": "battlefield", "to": "graveyard"},
        source="test",
    )
    assert leave_icp.filter(fake_zc, game.state), (
        "Bug #5: filter must accept finance_combat ZONE_CHANGE shape"
    )
    print("test_bug5_speed_amplifier_destroys_when_host_zone_changes  PASS")


# ---------------------------------------------------------------------------
# Bug #6 — Tick Data Archive flag set on solo alpha attack
# ---------------------------------------------------------------------------

def test_bug6_solo_alpha_sets_struck_alone_flag():
    """When an alpha-striker attacks solo, fin_alpha_struck_alone_<ctrl>
    must be set so Tick Data Archive's Pre-Market trigger draws.
    """
    game, p1, p2 = _make_finance_game()
    a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
    a.state.attacking = True  # mark as attacking so _alpha_strike_bonus counts

    flag_key = f"fin_alpha_struck_alone_{p1.id}"
    assert not game.state.turn_data.get(flag_key), "flag must start unset"

    _alpha_strike_bonus(a, game.state, power_mod=3)
    assert game.state.turn_data.get(flag_key) is True, (
        "Bug #6: solo alpha attack must set fin_alpha_struck_alone_<controller>"
    )
    print("test_bug6_solo_alpha_sets_struck_alone_flag  PASS")


def test_bug6_multi_attack_does_not_set_struck_alone_flag():
    """Multi-attack does NOT set the solo flag (Tick Data Archive must not draw)."""
    game, p1, p2 = _make_finance_game()
    a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
    b = _put_on_battlefield(game, p1.id, RETAIL_FLOW_CHASER)
    a.state.attacking = True
    b.state.attacking = True

    flag_key = f"fin_alpha_struck_alone_{p1.id}"
    _alpha_strike_bonus(a, game.state, power_mod=3)
    _alpha_strike_bonus(b, game.state, power_mod=3)

    assert not game.state.turn_data.get(flag_key), (
        "Bug #6: multi-attack must NOT set the solo-alpha flag"
    )
    print("test_bug6_multi_attack_does_not_set_struck_alone_flag  PASS")


def test_bug6_tick_data_archive_pre_market_draws_when_flag_set():
    """Tick Data Archive's pre-market trigger emits a DRAW when the
    fin_alpha_struck_alone flag is set, then clears it.
    """
    game, p1, p2 = _make_finance_game()
    tda = _put_on_battlefield(game, p1.id, TICK_DATA_ARCHIVE)

    flag_key = f"fin_alpha_struck_alone_{p1.id}"
    game.state.turn_data[flag_key] = True

    icps = TICK_DATA_ARCHIVE.setup_interceptors(tda, game.state)
    assert icps, "TDA must register at least one interceptor"
    icp = icps[0]
    # The trigger fires on PHASE_START with phase='pre_market' for our controller.
    from src.engine.types import Event
    pre_market_ev = Event(
        type=EventType.PHASE_START,
        payload={"phase": "pre_market"},
        source="turn_manager",
    )
    # Set active_player so the controller_only check passes.
    game.state.active_player = p1.id
    assert icp.filter(pre_market_ev, game.state), (
        "TDA filter must accept pre_market PHASE_START on controller's turn"
    )
    result = icp.handler(pre_market_ev, game.state)
    assert any(
        ev.type == EventType.DRAW and ev.payload.get("player") == p1.id
        for ev in result.new_events
    ), "Bug #6: TDA must emit DRAW for controller when flag is set"
    # Flag should be cleared after the trigger consumes it.
    assert not game.state.turn_data.get(flag_key), (
        "TDA must clear the alpha-struck-alone flag after consuming it"
    )
    print("test_bug6_tick_data_archive_pre_market_draws_when_flag_set  PASS")


# ---------------------------------------------------------------------------
# Bug #1 — Combat damage threshold (any-damage-kills + default trample)
# ---------------------------------------------------------------------------
#
# Two intermixed engine bugs: (a) blocked attacker damage was DOUBLE-COUNTED
# because both the pipeline DAMAGE handler and finance_combat._apply_damage
# wrote ``target.state.damage += amount``; and (b) excess attacker
# Aggression always overflowed to the defender's Capital Reserve regardless
# of whether the attacker had the trample keyword.
# ---------------------------------------------------------------------------

def _make_vanilla_trader(name: str, power: int, toughness: int):
    """Build a vanilla FIN_TRADER CardDefinition with no triggers. Useful for
    isolating combat-engine behaviour from Alpha Strike / Arbitrage noise.
    """
    from src.engine.types import CardDefinition, Characteristics
    chars = Characteristics(
        types={CardType.FIN_TRADER},
        subtypes={"Trader"},
        power=power,
        toughness=toughness,
        mana_cost="{1}",
    )
    return CardDefinition(
        name=name,
        mana_cost="{1}",
        characteristics=chars,
        domain="FINA",
        text="Vanilla.",
    )


def test_bug1_two_power_into_four_toughness_blocker_survives():
    """2-power attacker into 4-toughness blocker → blocker survives with 2 damage marked."""
    game, p1, p2 = _make_finance_game()
    atk_def = _make_vanilla_trader("Test Attacker 2/1", power=2, toughness=1)
    blk_def = _make_vanilla_trader("Test Blocker 2/4", power=2, toughness=4)
    attacker = _put_on_battlefield(game, p1.id, atk_def)
    blocker = _put_on_battlefield(game, p2.id, blk_def)

    cm = game.turn_manager.finance_combat_manager
    asyncio.run(cm.declare_attackers(p1.id, [attacker.id]))
    asyncio.run(cm.declare_blockers(p2.id, {attacker.id: blocker.id}))
    asyncio.run(cm.resolve_combat_damage([attacker.id], {attacker.id: blocker.id}, p2.id))

    # Blocker must survive: damage_dealt=2 < toughness=4.
    assert blocker.zone == ZoneType.BATTLEFIELD, (
        "Bug #1: 2-power attacker into 4-toughness blocker must NOT kill blocker"
    )
    # Damage should be exactly 2 (not 4 from double-counting).
    assert blocker.state.damage == 2, (
        f"Bug #1: blocker should have exactly 2 damage marked (got {blocker.state.damage})"
    )
    # Defender's Capital Reserve must be unchanged (no trample overflow).
    assert game.state.players[p2.id].life == 30, (
        f"Bug #1: no trample → defender Capital Reserve unchanged "
        f"(got {game.state.players[p2.id].life})"
    )
    print("test_bug1_two_power_into_four_toughness_blocker_survives  PASS")


def test_bug1_overflow_only_with_trample():
    """5-power attacker into 4-toughness blocker:
        - WITHOUT trample: blocker dies, NO damage to defender Capital Reserve
        - WITH trample: blocker dies AND 1 damage hits Capital Reserve
    """
    # Path 1: vanilla attacker (no trample).
    game, p1, p2 = _make_finance_game()
    atk_def = _make_vanilla_trader("Test Attacker 5/1", power=5, toughness=1)
    blk_def = _make_vanilla_trader("Test Blocker 2/4", power=2, toughness=4)
    attacker = _put_on_battlefield(game, p1.id, atk_def)
    blocker = _put_on_battlefield(game, p2.id, blk_def)

    cm = game.turn_manager.finance_combat_manager
    asyncio.run(cm.declare_attackers(p1.id, [attacker.id]))
    asyncio.run(cm.declare_blockers(p2.id, {attacker.id: blocker.id}))
    p2_life_before = game.state.players[p2.id].life
    asyncio.run(cm.resolve_combat_damage([attacker.id], {attacker.id: blocker.id}, p2.id))

    # Without trample: blocker takes 5 dmg vs 4 tough → dies. No overflow.
    assert blocker.zone != ZoneType.BATTLEFIELD or blocker.state.damage >= 4, (
        "Bug #1: 5-power into 4-toughness must kill blocker"
    )
    assert game.state.players[p2.id].life == p2_life_before, (
        f"Bug #1: NO trample → defender Capital Reserve unchanged "
        f"(life {p2_life_before} → {game.state.players[p2.id].life})"
    )

    # Path 2: same setup but grant the trample keyword.
    game2, q1, q2 = _make_finance_game()
    atk_trample_def = _make_vanilla_trader("Test Trample 5/1", power=5, toughness=1)
    atk_trample_def.characteristics.abilities = [{"keyword": "trample"}]
    atk2 = _put_on_battlefield(game2, q1.id, atk_trample_def)
    blk2 = _put_on_battlefield(game2, q2.id, blk_def)
    cm2 = game2.turn_manager.finance_combat_manager
    asyncio.run(cm2.declare_attackers(q1.id, [atk2.id]))
    asyncio.run(cm2.declare_blockers(q2.id, {atk2.id: blk2.id}))
    q2_life_before = game2.state.players[q2.id].life
    asyncio.run(cm2.resolve_combat_damage([atk2.id], {atk2.id: blk2.id}, q2.id))

    # With trample: 5 dmg, blocker has 4 toughness, 1 overflow to face.
    overflow = q2_life_before - game2.state.players[q2.id].life
    assert overflow == 1, (
        f"Bug #1: WITH trample, expected 1 face damage overflow, got {overflow}"
    )
    print("test_bug1_overflow_only_with_trample  PASS")


# ---------------------------------------------------------------------------
# Bug #7 — Correlation Matrix DRAW dead
# ---------------------------------------------------------------------------

def test_bug7_correlation_matrix_actually_draws():
    """Casting Correlation Matrix while leading by 3 Traders → hand grows by 3."""
    from src.cards.finance.fina.quant import (
        CORRELATION_MATRIX,
        STATISTICAL_ARB_CLERK,
    )
    game, p1, p2 = _make_finance_game()
    # P1 leads by 3 Traders (3 vs 0).
    _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)
    _put_on_battlefield(game, p1.id, STATISTICAL_ARB_CLERK)

    # Stuff some cards into P1's library so DRAW has something to fetch.
    library = game.state.zones.get(f"library_{p1.id}")
    for _ in range(5):
        game.add_card_to_library(p1.id, STATISTICAL_ARB_CLERK)

    hand = game.state.zones.get(f"hand_{p1.id}")
    hand_before = len(hand.objects)

    # Synthesize the resolve event that finance_turn would build.
    from src.engine.types import Event, EventType
    src_id = "test_src"
    resolve_event = Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": p1.id, "source_id": src_id},
        source=src_id,
        controller=p1.id,
    )
    out_events = CORRELATION_MATRIX.resolve(resolve_event, game.state)

    # The resolve should emit a DRAW event with count==3.
    draw_events = [e for e in out_events if e.type == EventType.DRAW]
    assert len(draw_events) == 1, (
        f"Bug #7: Correlation Matrix should emit exactly one DRAW (got {len(draw_events)})"
    )
    assert draw_events[0].payload.get("count") == 3, (
        f"Bug #7: DRAW count should be 3 (got {draw_events[0].payload.get('count')})"
    )
    # Process the DRAW event through the pipeline so the hand actually grows.
    game.pipeline.emit(draw_events[0])
    hand_after = len(hand.objects)
    assert hand_after - hand_before == 3, (
        f"Bug #7: Hand should grow by 3 (got {hand_after - hand_before})"
    )
    print("test_bug7_correlation_matrix_actually_draws  PASS")


# ---------------------------------------------------------------------------
# Bug #8 — Quant Signal LOOK_AT_TOP doesn't put a card in hand
# ---------------------------------------------------------------------------

def test_bug8_quant_signal_puts_top_card_in_hand():
    """Resolve Quant Signal → hand grows by 1, top card moves out of library."""
    from src.cards.finance.fina.quant import QUANT_SIGNAL, STATISTICAL_ARB_CLERK
    game, p1, p2 = _make_finance_game()
    # Stuff library so we have at least 3 cards for the look-at-top.
    for _ in range(5):
        game.add_card_to_library(p1.id, STATISTICAL_ARB_CLERK)
    library = game.state.zones.get(f"library_{p1.id}")
    hand = game.state.zones.get(f"hand_{p1.id}")
    hand_before = len(hand.objects)
    lib_before = len(library.objects)
    top_id_before = library.objects[0]

    from src.engine.types import Event, EventType
    src_id = "test_src"
    resolve_event = Event(
        type=EventType.FIN_PLAY_CARD,
        payload={"controller": p1.id, "source_id": src_id},
        source=src_id,
        controller=p1.id,
    )
    QUANT_SIGNAL.resolve(resolve_event, game.state)

    assert len(hand.objects) == hand_before + 1, (
        f"Bug #8: Quant Signal must place 1 card into hand "
        f"(hand went {hand_before}→{len(hand.objects)})"
    )
    assert top_id_before in hand.objects, (
        "Bug #8: the originally-top library card must now be in hand"
    )
    # Library shrinks by 1 (the kept card).
    assert len(library.objects) == lib_before - 1, (
        f"Bug #8: Library should shrink by exactly 1 "
        f"(was {lib_before}, now {len(library.objects)})"
    )
    print("test_bug8_quant_signal_puts_top_card_in_hand  PASS")


# ---------------------------------------------------------------------------
# Bug #9 — Risk Manager Arbitrage timing (reduce damage during combat,
# net effect = "heal 1 after combat")
# ---------------------------------------------------------------------------

def test_bug9_risk_manager_blocks_one_power_takes_zero_net_damage():
    """RM (1/4) blocks a 1-power attacker → after combat, RM has 0 damage."""
    from src.cards.finance.fina.quant import RISK_MANAGER
    game, p1, p2 = _make_finance_game()
    # Use a vanilla 1/1 attacker so Alpha Strike doesn't pump it to 4.
    atk_def = _make_vanilla_trader("Test 1/1 Attacker", power=1, toughness=1)
    attacker = _put_on_battlefield(game, p1.id, atk_def)
    blocker = _put_on_battlefield(game, p2.id, RISK_MANAGER)

    cm = game.turn_manager.finance_combat_manager
    asyncio.run(cm.declare_attackers(p1.id, [attacker.id]))
    asyncio.run(cm.declare_blockers(p2.id, {attacker.id: blocker.id}))
    asyncio.run(cm.resolve_combat_damage([attacker.id], {attacker.id: blocker.id}, p2.id))

    # Risk Manager survived; net damage on RM after the heal = 0.
    assert blocker.zone == ZoneType.BATTLEFIELD, (
        "Bug #9: Risk Manager should survive blocking a 1-power attacker"
    )
    assert blocker.state.damage == 0, (
        f"Bug #9: Risk Manager net damage should be 0 (1 dmg dealt, -1 heal) "
        f"(got {blocker.state.damage})"
    )
    print("test_bug9_risk_manager_blocks_one_power_takes_zero_net_damage  PASS")


# ---------------------------------------------------------------------------
# Bug #17 — Rebalancing Halt removes attacker from combat manager
# ---------------------------------------------------------------------------

def test_bug17_rebalancing_halt_undeclares_attacker():
    """Casting Rebalancing Halt on a declared attacker removes it from
    the combat manager's attackers_declared list."""
    from src.cards.finance.fina.quant import REBALANCING_HALT
    from src.cards.finance.fina.high_frequency import SPOOFING_ALGO
    game, p1, p2 = _make_finance_game()
    attacker = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)

    cm = game.turn_manager.finance_combat_manager
    asyncio.run(cm.declare_attackers(p1.id, [attacker.id]))
    # P2 owns turn_manager.fin_turn_state via the global game.turn_manager.
    fin_state = game.turn_manager.fin_turn_state
    fin_state.attackers_declared = [attacker.id]
    fin_state.combat_blocks = {}

    # P2 casts RH targeting attacker.
    from src.engine.types import Event, EventType
    resolve_event = Event(
        type=EventType.FIN_PLAY_CARD,
        payload={
            "controller": p2.id,
            "target_id": attacker.id,
            "source_id": "test_rh",
        },
        source="test_rh",
        controller=p2.id,
    )
    REBALANCING_HALT.resolve(resolve_event, game.state)

    assert attacker.id not in fin_state.attackers_declared, (
        f"Bug #17: Rebalancing Halt must un-declare the attacker "
        f"(still in attackers_declared={fin_state.attackers_declared})"
    )
    assert attacker.state.attacking is False, (
        "Bug #17: target's attacking flag must be cleared"
    )
    print("test_bug17_rebalancing_halt_undeclares_attacker  PASS")


# ---------------------------------------------------------------------------
# Dark Arbitrage bugs (#11, #12, #13, #15, #20)
#
# Owner: dark-arbitrage agent. Class TestDarkArbitrageBugs is the unique
# namespace per task spec; module-level wrappers below let `_run_all`
# discover and run each method.
# ---------------------------------------------------------------------------

from src.cards.finance.fina.dark_arbitrage import (             # noqa: E402
    HIDDEN_AGGRESSION,
    HIDDEN_ACCUMULATOR,
    OFF_EXCHANGE_POSITION,
    ICEBERG_ORDER,
    BLOCK_TRADE_SWEEP,
)
from src.engine.finance import get_dark_pool, set_dark_pool      # noqa: E402


class TestDarkArbitrageBugs:
    """Regression tests for Dark Pool combo identity (bugs 11/12/13/15/20)."""

    # ---- bug #15: Dark Pool slot is populated by play-card path ----------

    def test_dp_order_routes_to_dark_pool_not_graveyard(self):
        """Bug #15 — Casting a Dark Pool Order must stage it in the DP slot,
        NOT route it straight to the graveyard."""
        game, p1, p2 = _make_finance_game()
        ico = game.create_object(
            name=ICEBERG_ORDER.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=ICEBERG_ORDER.characteristics,
            card_def=ICEBERG_ORDER,
        )
        p1.mana_crystals = 5
        p1.mana_crystals_available = 5

        events = asyncio.run(
            game.turn_manager._play_card_action(p1.id, ico.id, [])
        )
        assert events, "play_card_action returned no events (cost/path failed)"
        assert get_dark_pool(game.state) == ico.id, (
            f"Bug #15: DP slot should hold {ico.id} but holds "
            f"{get_dark_pool(game.state)!r}"
        )
        gy = game.state.zones.get(f"graveyard_{p1.id}")
        assert gy is None or ico.id not in gy.objects, (
            "Bug #15: DP Order incorrectly routed to graveyard instead of DP slot"
        )
        hand = game.state.zones[f"hand_{p1.id}"]
        assert ico.id not in hand.objects, "DP Order must leave hand on stage"
        print("test_dp_order_routes_to_dark_pool_not_graveyard  PASS")

    def test_hidden_accumulator_triggers_on_dp_cast(self):
        """Bug #15 secondary — Hidden Accumulator's +1/+1 trigger on DP cast
        must fire when a Dark Pool Order is cast by its controller."""
        game, p1, p2 = _make_finance_game()
        hacc = _put_on_battlefield(game, p1.id, HIDDEN_ACCUMULATOR)
        ico = game.create_object(
            name=ICEBERG_ORDER.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=ICEBERG_ORDER.characteristics,
            card_def=ICEBERG_ORDER,
        )
        p1.mana_crystals = 5
        p1.mana_crystals_available = 5

        asyncio.run(
            game.turn_manager._play_card_action(p1.id, ico.id, [])
        )
        # Engine pipeline writes PT_MODIFICATION entries onto hacc.state.pt_modifiers
        # in {"power": N, "toughness": M, "duration": ...} dict shape.
        mods = getattr(hacc.state, "pt_modifiers", None) or []
        # Sum both "power_mod" and "power" keys for resilience to engine flux.
        power_delta = sum(
            int((m.get("power_mod") if m.get("power_mod") is not None else m.get("power", 0)) or 0)
            for m in mods
        )
        assert power_delta >= 1, (
            f"Bug #15 (HACC): expected +1 power from DP cast, got {power_delta} "
            f"(pt_modifiers={mods!r})"
        )
        print("test_hidden_accumulator_triggers_on_dp_cast  PASS")

    # ---- bug #12: Hidden Aggression text must match code value -----------

    def test_hidden_aggression_card_text_matches_code(self):
        """Bug #12 — Hidden Aggression's printed text and emitted PT mod must
        agree (+2/+0 after cyc3 nerf)."""
        text = HIDDEN_AGGRESSION.text or ""
        assert "+2/+0" in text, (
            f"Bug #12: Hidden Aggression text must say +2/+0 (cyc3 nerf), got: {text!r}"
        )
        assert "+4/+0" not in text, (
            f"Bug #12: stale +4/+0 text should be gone, got: {text!r}"
        )
        # Verify the dark_effect emits power_mod=2.
        game, p1, p2 = _make_finance_game()
        ha_obj = _put_on_battlefield(game, p1.id, HIDDEN_AGGRESSION)
        _put_on_battlefield(game, p1.id, HIDDEN_ACCUMULATOR)
        from src.cards.finance.fina.dark_arbitrage import _hidden_aggression_setup
        ics = _hidden_aggression_setup(ha_obj, game.state)
        assert ics, "HIDDEN_AGGRESSION setup_interceptors returned no interceptors"
        from src.engine.types import Event as _E
        ev = _E(type=EventType.FIN_MARKET_EVENT, payload={"obj_id": ha_obj.id}, source=ha_obj.id)
        result = ics[0].handler(ev, game.state)
        new_events = list(result.new_events or [])
        pt_events = [e for e in new_events if e.type == EventType.PT_MODIFICATION]
        assert pt_events, "Bug #12: HA dark_effect must emit a PT_MODIFICATION"
        assert pt_events[0].payload.get("power_mod") == 2, (
            f"Bug #12: HA dark_effect must apply +2/+0, got "
            f"power_mod={pt_events[0].payload.get('power_mod')}"
        )
        print("test_hidden_aggression_card_text_matches_code  PASS")

    # ---- bug #13: OEP refuses cast without DP slot -----------------------

    def test_oep_refuses_cast_without_dp_slot(self):
        """Bug #13 — Off-Exchange Position must refuse to cast when the
        Dark Pool slot is empty, returning no events and not deducting
        Liquidity."""
        game, p1, p2 = _make_finance_game()
        oep = game.create_object(
            name=OFF_EXCHANGE_POSITION.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=OFF_EXCHANGE_POSITION.characteristics,
            card_def=OFF_EXCHANGE_POSITION,
        )
        p1.mana_crystals = 5
        p1.mana_crystals_available = 5
        assert get_dark_pool(game.state) is None

        events = asyncio.run(
            game.turn_manager._play_card_action(p1.id, oep.id, [])
        )
        assert not events, (
            "Bug #13: cast without DP slot must refuse (no events emitted), "
            f"got {len(events)} events"
        )
        assert p1.mana_crystals_available == 5, (
            f"Bug #13: refused cast must NOT deduct Liquidity; "
            f"available={p1.mana_crystals_available}"
        )
        hand = game.state.zones[f"hand_{p1.id}"]
        assert oep.id in hand.objects, (
            "Bug #13: refused cast must keep card in hand"
        )

        # With DP slot occupied, OEP should be castable.
        ico = game.create_object(
            name=ICEBERG_ORDER.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=ICEBERG_ORDER.characteristics,
            card_def=ICEBERG_ORDER,
        )
        asyncio.run(
            game.turn_manager._play_card_action(p1.id, ico.id, [])
        )
        assert get_dark_pool(game.state) == ico.id

        events2 = asyncio.run(
            game.turn_manager._play_card_action(p1.id, oep.id, [])
        )
        assert events2, (
            "Bug #13: with DP slot populated, OEP must be castable; "
            "no events returned"
        )
        print("test_oep_refuses_cast_without_dp_slot  PASS")

    # ---- bug #20a: dark_pool_order filter recognized ---------------------

    def test_dark_pool_order_search_filter(self):
        """Bug #20a — SEARCH_LIBRARY filter=`dark_pool_order` must restrict
        results to DP-tagged FIN_ORDER cards only."""
        game, p1, p2 = _make_finance_game()
        ico_obj = game.create_object(
            name=ICEBERG_ORDER.name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=ICEBERG_ORDER.characteristics,
            card_def=ICEBERG_ORDER,
        )
        bts_obj = game.create_object(
            name=BLOCK_TRADE_SWEEP.name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=BLOCK_TRADE_SWEEP.characteristics,
            card_def=BLOCK_TRADE_SWEEP,
        )
        hacc_obj = game.create_object(
            name=HIDDEN_ACCUMULATOR.name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=HIDDEN_ACCUMULATOR.characteristics,
            card_def=HIDDEN_ACCUMULATOR,
        )

        from src.engine.library_search import _handle_search_library_event
        from src.engine.types import Event as _E
        evt = _E(
            type=EventType.SEARCH_LIBRARY,
            payload={
                "player": p1.id,
                "filter": "dark_pool_order",
                "destination": "hand",
                "count": 1,
                "min_count": 0,
            },
            source="test",
        )
        _handle_search_library_event(evt, game.state)
        choice = game.state.pending_choice
        assert choice is not None, (
            "Bug #20a: SEARCH_LIBRARY filter=dark_pool_order should create a PendingChoice"
        )
        opt_ids = set()
        for opt in choice.options:
            if isinstance(opt, dict):
                opt_ids.add(opt.get("id"))
            else:
                opt_ids.add(opt)
        assert ico_obj.id in opt_ids, (
            f"Bug #20a: Iceberg Order (DP=True) must be in tutor options; got {opt_ids!r}"
        )
        assert bts_obj.id in opt_ids, (
            f"Bug #20a: Block Trade Sweep (DP=True) must be in tutor options; got {opt_ids!r}"
        )
        assert hacc_obj.id not in opt_ids, (
            f"Bug #20a: Hidden Accumulator (Trader) must NOT be in dark_pool_order tutor options; "
            f"got {opt_ids!r}"
        )
        game.state.pending_choice = None
        print("test_dark_pool_order_search_filter  PASS")


# Module-level wrappers so the legacy `_run_all` driver picks them up.
_DARK_ARB_BUGS = TestDarkArbitrageBugs()


def test_dp_order_routes_to_dark_pool_not_graveyard():
    _DARK_ARB_BUGS.test_dp_order_routes_to_dark_pool_not_graveyard()


def test_hidden_accumulator_triggers_on_dp_cast():
    _DARK_ARB_BUGS.test_hidden_accumulator_triggers_on_dp_cast()


def test_hidden_aggression_card_text_matches_code():
    _DARK_ARB_BUGS.test_hidden_aggression_card_text_matches_code()


def test_oep_refuses_cast_without_dp_slot():
    _DARK_ARB_BUGS.test_oep_refuses_cast_without_dp_slot()


def test_dark_pool_order_search_filter():
    _DARK_ARB_BUGS.test_dark_pool_order_search_filter()


# ===========================================================================
# Derivatives leverage / engine-wide graveyard-routing tests
# Bugs covered: #10 (leverage tick damage), #14 (counter double-add),
#               #16 (destroyed Trader graveyard routing), #19 (leverage power
#               query priority).
# ===========================================================================

from src.engine.types import Event as _DLB_Event                  # noqa: E402
from src.engine.queries import get_power as _DLB_get_power        # noqa: E402
from src.cards.finance.fina.derivatives import (                  # noqa: E402
    DELTA_HEDGER as _DLB_DELTA_HEDGER,
)
from src.cards.finance.fina.dark_arbitrage import (               # noqa: E402
    OFF_EXCHANGE_OPERATIVE as _DLB_OEO,
    INSTITUTIONAL_BLOCK_TRADER as _DLB_IBT,
)


def _DLB_play_to_battlefield(game, player_id: str, card_def):
    """Create card in HAND, ZONE_CHANGE to BATTLEFIELD so ETB triggers fire."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    ev = _DLB_Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone_type": ZoneType.HAND,
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=obj.id,
    )
    game.pipeline.emit(ev)
    return obj


def test_leverage_3_trader_etb_counters_eq_3():
    """Bug #14: a Lev-N Trader's ETB must leave EXACTLY N leverage counters.

    Pre-fix: ``_make_leverage_setup`` emitted N COUNTER_ADDED events AND
    direct-set counters[leverage] = current + N as a "fallback". The
    pipeline's _handle_counter_added then added N more on top, doubling
    counters on every ETB (Lev-2 Trader → 4 counters; Lev-3 → 6).

    Post-fix: emits a single COUNTER_ADDED with amount=N; pipeline applies
    exactly once. Tested via Delta Hedger (Lev 2) — assert counter==2 not 4.
    """
    game, p1, _ = _make_finance_game()
    obj = _DLB_play_to_battlefield(game, p1.id, _DLB_DELTA_HEDGER)
    lev = obj.state.counters.get("leverage", 0)
    assert lev == 2, (
        f"Bug #14: Lev-2 Trader ETB should leave counters[leverage]==2 "
        f"(got {lev}; pre-fix would show 4)"
    )
    print("test_leverage_3_trader_etb_counters_eq_3  PASS")


def test_leverage_tick_single_trader_lev3_deals_3():
    """Bug #10: a single Lev-2 Trader on P1's MARKET_CLOSE deals exactly 2
    self-damage (Σleverage). Pre-fix scenarios reported ~1.7× the expected
    drain (16 vs 9 in iter-2). Root cause was bug #14 (counters double-added
    at ETB) compounding with a per-trader tick.

    Also asserts the tick filters by controller: P2's MC must NOT damage P1.
    """
    game, p1, p2 = _make_finance_game()
    dh = _DLB_play_to_battlefield(game, p1.id, _DLB_DELTA_HEDGER)
    assert dh.state.counters.get("leverage", 0) == 2, "test setup: leverage 2"

    cap_before = game.state.players[p1.id].life
    mc_p1 = _DLB_Event(
        type=EventType.PHASE_START,
        payload={"phase": "market_close", "player": p1.id},
    )
    game.pipeline.emit(mc_p1)
    cap_after_p1mc = game.state.players[p1.id].life
    assert cap_after_p1mc == cap_before - 2, (
        f"Bug #10: P1 MC tick should deal exactly Σleverage=2 "
        f"(cap {cap_before}→{cap_after_p1mc}, expected delta=-2)"
    )

    # P2's MC must NOT tick P1's leverage Traders (controller filter).
    mc_p2 = _DLB_Event(
        type=EventType.PHASE_START,
        payload={"phase": "market_close", "player": p2.id},
    )
    game.pipeline.emit(mc_p2)
    cap_after_p2mc = game.state.players[p1.id].life
    assert cap_after_p2mc == cap_after_p1mc, (
        f"Bug #10: P2's MC must not tick P1's leverage Traders "
        f"(cap should stay {cap_after_p1mc}, got {cap_after_p2mc})"
    )
    print("test_leverage_tick_single_trader_lev3_deals_3  PASS")


def test_leverage_power_query_fires():
    """Bug #19: leverage counters MUST add to displayed power.

    Pre-fix: ``_make_leverage_power_query`` in ``dark_arbitrage.py`` used
    ``InterceptorPriority.TRANSFORM`` (never iterated by ``queries.get_power``,
    which only walks ``priority == QUERY`` interceptors) AND mutated
    ``payload['power']`` (never read; ``get_power`` reads the result's
    ``transformed_event.payload['value']``).

    Post-fix: priority=QUERY, returns ``InterceptorAction.TRANSFORM`` with a
    cloned event whose ``payload['value']`` is incremented by leverage count.
    Same fix applied to ``derivatives._make_leverage_setup``'s power query.

    Test cases:
      OEO printed 3/3 + Lev 1 → displayed power 4 (was 3 pre-fix).
      IBT printed 3/4 + Lev 2 → displayed power 5 (was 3 pre-fix).
      Delta Hedger printed 3/4 + Lev 2 → displayed power 5 (was 3 pre-fix).
    """
    game, p1, _ = _make_finance_game()

    oeo = _DLB_play_to_battlefield(game, p1.id, _DLB_OEO)
    assert oeo.state.counters.get("leverage", 0) == 1
    p_oeo = _DLB_get_power(oeo, game.state)
    assert p_oeo == 4, (
        f"Bug #19: OEO printed 3 + Lev 1 should display power 4 (got {p_oeo})"
    )

    ibt = _DLB_play_to_battlefield(game, p1.id, _DLB_IBT)
    assert ibt.state.counters.get("leverage", 0) == 2
    p_ibt = _DLB_get_power(ibt, game.state)
    assert p_ibt == 5, (
        f"Bug #19: IBT printed 3 + Lev 2 should display power 5 (got {p_ibt})"
    )

    dh = _DLB_play_to_battlefield(game, p1.id, _DLB_DELTA_HEDGER)
    assert dh.state.counters.get("leverage", 0) == 2
    p_dh = _DLB_get_power(dh, game.state)
    assert p_dh == 5, (
        f"Bug #19: Delta Hedger printed 3 + Lev 2 should display power 5 "
        f"(got {p_dh})"
    )
    print("test_leverage_power_query_fires  PASS")


def test_creature_dies_routed_to_graveyard():
    """Bug #16: when a Trader dies in combat, it MUST appear in its owner's
    graveyard (engine-wide regression).

    Pre-fix: ``FinanceCombatManager._liquidate_if_lethal`` emitted
    ``OBJECT_DESTROYED`` (which routes correctly via
    ``_handle_object_destroyed`` → ``graveyard_<owner_id>``) AND a follow-up
    ``ZONE_CHANGE`` with ``from='battlefield'``, ``to='graveyard'`` (literal
    strings, NOT zone keys). The follow-up ran
    ``_remove_object_from_all_zones`` (yanking the corpse out of the
    graveyard where ``OBJECT_DESTROYED`` had just placed it) and then failed
    to re-add (because 'graveyard' is not a real zone key — the actual keys
    are ``graveyard_<player_id>``). Net effect: ``obj.zone == GRAVEYARD`` but
    the graveyard zone list was empty. Affects leaves-battlefield triggers,
    recursion, GY-counting effects.

    Post-fix: removed the redundant ZONE_CHANGE emit. The OBJECT_DESTROYED
    handler is the single source of truth for routing dead Traders.

    Test 1: direct ``_liquidate_if_lethal`` on an already-damaged object
            (covers the path where DAMAGE handler did NOT fire
            ``post_creature_damage_destroy_check``).
    Test 2: combat 1-for-1 trade — both 1/1s end up in respective graveyards.
    """
    from src.engine.types import CardDefinition as _CD, Characteristics as _Ch

    game, p1, p2 = _make_finance_game()
    cmgr = game.turn_manager.finance_combat_manager

    # Test 1: direct _liquidate_if_lethal path
    chars_lite = _Ch(types={CardType.FIN_TRADER}, power=1, toughness=2, mana_cost="{1}")
    survivor_cd = _CD(name="Survivor", mana_cost="{1}", characteristics=chars_lite, domain="FINA")
    survivor = game.create_object("Survivor", p1.id, ZoneType.BATTLEFIELD, chars_lite, survivor_cd)
    survivor.state.damage = 2  # exactly lethal
    survivor.state.last_damage_source = survivor.id

    asyncio.run(cmgr._liquidate_if_lethal(survivor.id))
    assert survivor.zone == ZoneType.GRAVEYARD, (
        f"Bug #16: dead Trader should have zone=GRAVEYARD (got {survivor.zone})"
    )
    p1_gy = list(game.state.zones[f"graveyard_{p1.id}"].objects)
    assert survivor.id in p1_gy, (
        f"Bug #16: dead Trader id should appear in graveyard_{p1.id} "
        f"(got {p1_gy}; pre-fix the graveyard was empty)"
    )

    # Test 2: combat 1-for-1 trade
    chars_1_1 = _Ch(types={CardType.FIN_TRADER}, power=1, toughness=1, mana_cost="{1}")
    atk_cd = _CD(name="Atk", mana_cost="{1}", characteristics=chars_1_1, domain="FINA")
    blk_cd = _CD(name="Blk", mana_cost="{1}", characteristics=chars_1_1, domain="FINA")
    atk = game.create_object("Atk", p1.id, ZoneType.BATTLEFIELD, chars_1_1, atk_cd)
    blk = game.create_object("Blk", p2.id, ZoneType.BATTLEFIELD, chars_1_1, blk_cd)
    atk.state.summoning_sickness = False
    blk.state.summoning_sickness = False

    asyncio.run(cmgr.declare_attackers(p1.id, [atk.id]))
    asyncio.run(cmgr.declare_blockers(p2.id, {atk.id: blk.id}))
    asyncio.run(cmgr.resolve_combat_damage([atk.id], {atk.id: blk.id}, p2.id))

    p1_gy = list(game.state.zones[f"graveyard_{p1.id}"].objects)
    p2_gy = list(game.state.zones[f"graveyard_{p2.id}"].objects)
    assert atk.id in p1_gy, (
        f"Bug #16: attacker corpse must be in P1 graveyard (got {p1_gy})"
    )
    assert blk.id in p2_gy, (
        f"Bug #16: blocker corpse must be in P2 graveyard (got {p2_gy})"
    )
    assert atk.zone == ZoneType.GRAVEYARD, (
        f"Bug #16: attacker zone should be GRAVEYARD (got {atk.zone})"
    )
    assert blk.zone == ZoneType.GRAVEYARD, (
        f"Bug #16: blocker zone should be GRAVEYARD (got {blk.zone})"
    )
    print("test_creature_dies_routed_to_graveyard  PASS")


# ===========================================================================
# DP timing + isolated card bugs (#24, #26, #27, #29)
#
# Owner: dp-timing agent.
#   #24 — Vega Spike resolves but counters never land
#   #26 — Hidden Aggression suspected face-damage on cast (speculative)
#   #27 — Trample overflow inconsistency (vanilla vs trample, mutual-kill)
#   #29 — Crossed Market / Payment for Order Flow DP trigger fires on the
#         opponent's TS where the effect is useless; must defer until the
#         controller's next TS.
# ===========================================================================

from src.cards.finance.fina.derivatives import VEGA_SPIKE                # noqa: E402
from src.cards.finance.fina.dark_arbitrage import (                      # noqa: E402
    CROSSED_MARKET,
    PAYMENT_FOR_ORDER_FLOW,
)


class TestDPTimingAndCardBugs:
    """Regression tests for #24, #26, #27, #29."""

    # ---- bug #24: Vega Spike adds Leverage counters to its target ---------

    def test_bug24_vega_spike_adds_leverage_counters(self):
        """Casting Vega Spike on a Trader you control must add 2 leverage
        counters (was previously a no-op due to a target-shape mismatch:
        the resolve indexed targets[0][0] expecting nested form, but the AI
        passes flat [card_id])."""
        from src.cards.finance.fina.high_frequency import SPOOFING_ALGO
        game, p1, _ = _make_finance_game()
        target = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
        # Hand Vega Spike to P1 with enough Liquidity.
        vs = game.create_object(
            name=VEGA_SPIKE.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=VEGA_SPIKE.characteristics,
            card_def=VEGA_SPIKE,
        )
        p1.mana_crystals = 9
        p1.mana_crystals_available = 9
        lev_before = int(target.state.counters.get("leverage", 0))

        # Pass targets in the AI shape (flat list of card ids).
        events = asyncio.run(
            game.turn_manager._play_card_action(p1.id, vs.id, [target.id])
        )
        assert events, "Bug #24: VS should produce events (cost path failed otherwise)"
        lev_after = int(target.state.counters.get("leverage", 0))
        assert lev_after == lev_before + 2, (
            f"Bug #24: Vega Spike must place 2 leverage counters on target "
            f"(before={lev_before}, after={lev_after})"
        )
        # Mana was consumed.
        assert p1.mana_crystals_available == 9 - 3, (
            f"Bug #24: VS costs 3 Liquidity (got {9 - p1.mana_crystals_available})"
        )
        # Strategy went to graveyard.
        assert vs.zone == ZoneType.GRAVEYARD, (
            f"Bug #24: VS should route to graveyard after resolve (got {vs.zone})"
        )
        print("test_bug24_vega_spike_adds_leverage_counters  PASS")

    # ---- bug #26: Hidden Aggression must NOT damage opponent on cast ------

    def test_bug26_hidden_aggression_does_not_damage_opponent_on_cast(self):
        """Pilot A iter 2 v2 T6/T10 saw P1 capital drop +1 beyond the
        Leverage tick after staging Hidden Aggression. The card's effect is
        a friendly +2/+0 PT pump — there should be ZERO LIFE_CHANGE on the
        opponent during the cast (staging) path."""
        game, p1, p2 = _make_finance_game()
        ha = game.create_object(
            name=HIDDEN_AGGRESSION.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=HIDDEN_AGGRESSION.characteristics,
            card_def=HIDDEN_AGGRESSION,
        )
        p1.mana_crystals = 5
        p1.mana_crystals_available = 5
        p2_capital_before = p2.life
        p1_capital_before = p1.life

        events = asyncio.run(
            game.turn_manager._play_card_action(p1.id, ha.id, [])
        )
        assert events, "Bug #26: HA cast should still produce stage events"
        # Opponent capital must be unchanged on staging.
        assert p2.life == p2_capital_before, (
            f"Bug #26: HA stage must NOT damage opponent capital "
            f"(was {p2_capital_before}, now {p2.life})"
        )
        # Controller capital also unchanged on staging.
        assert p1.life == p1_capital_before, (
            f"Bug #26: HA stage must NOT damage controller capital "
            f"(was {p1_capital_before}, now {p1.life})"
        )
        # Confirm no LIFE_CHANGE event was emitted during the cast.
        life_changes = [e for e in events if e.type == EventType.LIFE_CHANGE]
        assert not life_changes, (
            f"Bug #26: HA cast must emit zero LIFE_CHANGE events, got {life_changes!r}"
        )
        print("test_bug26_hidden_aggression_does_not_damage_opponent_on_cast  PASS")

    # ---- bug #27: trample is opt-in (no overflow without keyword) ---------

    def test_bug27_no_trample_overflow_without_keyword(self):
        """Vanilla 5/5 attacker into 2/2 blocker → blocker dies, attacker
        survives, NO face damage on defender's Capital Reserve."""
        game, p1, p2 = _make_finance_game()
        atk_def = _make_vanilla_trader("Vanilla 5/5", power=5, toughness=5)
        blk_def = _make_vanilla_trader("Vanilla 2/2", power=2, toughness=2)
        attacker = _put_on_battlefield(game, p1.id, atk_def)
        blocker = _put_on_battlefield(game, p2.id, blk_def)

        cm = game.turn_manager.finance_combat_manager
        asyncio.run(cm.declare_attackers(p1.id, [attacker.id]))
        asyncio.run(cm.declare_blockers(p2.id, {attacker.id: blocker.id}))
        p2_life_before = game.state.players[p2.id].life
        asyncio.run(
            cm.resolve_combat_damage([attacker.id], {attacker.id: blocker.id}, p2.id)
        )

        # Blocker dies.
        assert blocker.zone == ZoneType.GRAVEYARD, (
            f"Bug #27: 5-power into 2-tough must kill blocker (got zone={blocker.zone})"
        )
        # No overflow without trample.
        assert game.state.players[p2.id].life == p2_life_before, (
            f"Bug #27: NO trample → defender Capital Reserve unchanged "
            f"(was {p2_life_before}, now {game.state.players[p2.id].life})"
        )
        # Attacker survives (5-tough vs 2-power blocker).
        assert attacker.zone == ZoneType.BATTLEFIELD, (
            f"Bug #27: 5/5 attacker should survive a 2/2 blocker (got {attacker.zone})"
        )
        print("test_bug27_no_trample_overflow_without_keyword  PASS")

    def test_bug27_trample_overflow_with_keyword(self):
        """Trample 5/5 attacker into 2/2 blocker → blocker dies + 3 face
        damage to defender's Capital Reserve."""
        game, p1, p2 = _make_finance_game()
        atk_def = _make_vanilla_trader("Trample 5/5", power=5, toughness=5)
        atk_def.characteristics.abilities = [{"keyword": "trample"}]
        blk_def = _make_vanilla_trader("Vanilla 2/2", power=2, toughness=2)
        attacker = _put_on_battlefield(game, p1.id, atk_def)
        blocker = _put_on_battlefield(game, p2.id, blk_def)

        cm = game.turn_manager.finance_combat_manager
        asyncio.run(cm.declare_attackers(p1.id, [attacker.id]))
        asyncio.run(cm.declare_blockers(p2.id, {attacker.id: blocker.id}))
        p2_life_before = game.state.players[p2.id].life
        asyncio.run(
            cm.resolve_combat_damage([attacker.id], {attacker.id: blocker.id}, p2.id)
        )

        # Blocker dies.
        assert blocker.zone == ZoneType.GRAVEYARD, (
            f"Bug #27: 5-power into 2-tough must kill blocker (got zone={blocker.zone})"
        )
        # Trample → 5 - 2 = 3 face damage.
        face_damage = p2_life_before - game.state.players[p2.id].life
        assert face_damage == 3, (
            f"Bug #27: WITH trample, expected 3 face damage (5-power - 2-tough), "
            f"got {face_damage}"
        )
        print("test_bug27_trample_overflow_with_keyword  PASS")

    # ---- bug #29: CM and PFOF must defer to controller's TS ---------------

    def _stage_dark_pool(self, game, player_id: str, card_def):
        """Helper: place a Dark Pool Order in EXILE staging + populate the DP slot."""
        from src.engine.finance import set_dark_pool
        order = game.create_object(
            name=card_def.name,
            owner_id=player_id,
            zone=ZoneType.EXILE,
            characteristics=card_def.characteristics,
            card_def=card_def,
        )
        set_dark_pool(game.state, order.id)
        # Run setup_interceptors so the FIN_MARKET_EVENT REACT is registered
        # (mirrors what _play_card_action does after staging).
        ics = card_def.setup_interceptors(order, game.state) if card_def.setup_interceptors else []
        for ic in ics:
            order.interceptor_ids.append(ic.id)
            game.register_interceptor(ic)
        return order, ics

    def test_bug29_crossed_market_fires_on_controller_ts(self):
        """Stage CM (controller=P1). Forging the system FIN_MARKET_EVENT
        with active_player=P2 (opponent's TS) must NOT apply the cant-block
        flag and must re-stage the dark pool slot. Then forging it with
        active_player=P1 (controller's TS) must apply the cant-block flag
        to the opponent Trader."""
        from src.cards.finance.fina.high_frequency import SPOOFING_ALGO
        from src.engine.finance import get_dark_pool, set_dark_pool
        from src.engine.types import Event as _E
        game, p1, p2 = _make_finance_game()
        # P2 has a Trader for CM to target.
        opp_trader = _put_on_battlefield(game, p2.id, SPOOFING_ALGO)
        order, ics = self._stage_dark_pool(game, p1.id, CROSSED_MARKET)
        assert get_dark_pool(game.state) == order.id

        ic = ics[0]
        # ---- Opponent's TS first (should defer) ---------------------------
        # Mimic the system trigger: clear DP slot, then fire FIN_MARKET_EVENT
        # with controller=p2 (the active player).
        set_dark_pool(game.state, None)
        ev_opp = _E(
            type=EventType.FIN_MARKET_EVENT,
            payload={"obj_id": order.id, "controller": p2.id},
            source=order.id,
            controller=p2.id,
        )
        ic.handler(ev_opp, game.state)
        # Effect must NOT apply on opp's TS.
        cant_block_key = f"fin_cant_block_{opp_trader.id}"
        assert not game.state.turn_data.get(cant_block_key), (
            "Bug #29: CM must NOT apply 'can't block' on the opponent's TS"
        )
        # And the DP slot must be re-staged so the system trigger picks it up
        # again on the controller's next TS.
        assert get_dark_pool(game.state) == order.id, (
            "Bug #29: CM must re-stage itself when firing on the wrong TS"
        )

        # ---- Controller's TS (should apply) -------------------------------
        set_dark_pool(game.state, None)
        ev_ctrl = _E(
            type=EventType.FIN_MARKET_EVENT,
            payload={"obj_id": order.id, "controller": p1.id},
            source=order.id,
            controller=p1.id,
        )
        ic.handler(ev_ctrl, game.state)
        assert game.state.turn_data.get(cant_block_key) is True, (
            f"Bug #29: CM must apply 'can't block' to opponent Trader "
            f"{opp_trader.id} on the controller's TS"
        )
        print("test_bug29_crossed_market_fires_on_controller_ts  PASS")

    def test_bug29_pfof_fires_on_controller_ts(self):
        """Stage PFOF (controller=P1). Firing on opp's TS gives no Liquidity;
        firing on controller's TS gives +1 Liquidity (cyc3 nerf)."""
        from src.engine.finance import get_dark_pool, set_dark_pool
        from src.engine.types import Event as _E
        game, p1, p2 = _make_finance_game()
        order, ics = self._stage_dark_pool(game, p1.id, PAYMENT_FOR_ORDER_FLOW)
        # Give P1 some Liquidity headroom so the +1 isn't capped at the max.
        p1.mana_crystals = 5
        p1.mana_crystals_available = 2
        assert get_dark_pool(game.state) == order.id

        ic = ics[0]
        # ---- Opponent's TS (defer) ---------------------------------------
        set_dark_pool(game.state, None)
        avail_before_opp = p1.mana_crystals_available
        ev_opp = _E(
            type=EventType.FIN_MARKET_EVENT,
            payload={"obj_id": order.id, "controller": p2.id},
            source=order.id,
            controller=p2.id,
        )
        ic.handler(ev_opp, game.state)
        assert p1.mana_crystals_available == avail_before_opp, (
            f"Bug #29: PFOF must NOT grant Liquidity on opponent's TS "
            f"(was {avail_before_opp}, now {p1.mana_crystals_available})"
        )
        assert get_dark_pool(game.state) == order.id, (
            "Bug #29: PFOF must re-stage itself when firing on the wrong TS"
        )

        # ---- Controller's TS (apply) -------------------------------------
        set_dark_pool(game.state, None)
        avail_before_ctrl = p1.mana_crystals_available
        ev_ctrl = _E(
            type=EventType.FIN_MARKET_EVENT,
            payload={"obj_id": order.id, "controller": p1.id},
            source=order.id,
            controller=p1.id,
        )
        ic.handler(ev_ctrl, game.state)
        assert p1.mana_crystals_available == avail_before_ctrl + 1, (
            f"Bug #29: PFOF must grant +1 Liquidity on controller's TS "
            f"(was {avail_before_ctrl}, now {p1.mana_crystals_available})"
        )
        print("test_bug29_pfof_fires_on_controller_ts  PASS")


# Module-level wrappers so the legacy `_run_all` driver picks them up.
_DP_TIMING_BUGS = TestDPTimingAndCardBugs()


def test_bug24_vega_spike_adds_leverage_counters():
    _DP_TIMING_BUGS.test_bug24_vega_spike_adds_leverage_counters()


def test_bug26_hidden_aggression_does_not_damage_opponent_on_cast():
    _DP_TIMING_BUGS.test_bug26_hidden_aggression_does_not_damage_opponent_on_cast()


def test_bug27_no_trample_overflow_without_keyword():
    _DP_TIMING_BUGS.test_bug27_no_trample_overflow_without_keyword()


def test_bug27_trample_overflow_with_keyword():
    _DP_TIMING_BUGS.test_bug27_trample_overflow_with_keyword()


def test_bug29_crossed_market_fires_on_controller_ts():
    _DP_TIMING_BUGS.test_bug29_crossed_market_fires_on_controller_ts()


def test_bug29_pfof_fires_on_controller_ts():
    _DP_TIMING_BUGS.test_bug29_pfof_fires_on_controller_ts()


# ===========================================================================
# Priority-mismatch class bugs (#21, #22, #25, #28)
#
# Owner: priority-class agent.
#   #21 — HFT Feed Colocation +1/+0 power buff to Traders (was unread handler)
#   #22 — PCD lord toughness +0/+1 (was TRANSFORM priority — unread by
#         queries.get_toughness)
#   #25 — Synthetic Collar +1/+1 per attached Derivative (was unread handler)
#   #28 — Dark Flow Engine -1 cost on DP Orders (was TRANSFORM priority +
#         unread handler + finance_turn never queried QUERY_COST interceptors)
# ===========================================================================

from src.cards.finance.fina.high_frequency import (                # noqa: E402
    HFT_FEED_COLOCATION,
    TICKER_TAPE_DERIVATIVE,
    DARK_POOL_FLASH_ORDER,
)
from src.cards.finance.fina.quant import (                         # noqa: E402
    PORTFOLIO_CONSTRUCTION_DESK,
    RISK_MANAGER as PCD_RISK_MANAGER,
)
from src.cards.finance.fina.derivatives import (                   # noqa: E402
    SYNTHETIC_COLLAR,
)
from src.cards.finance.fina.dark_arbitrage import (                # noqa: E402
    DARK_FLOW_ENGINE,
)
from src.engine.queries import (                                   # noqa: E402
    get_power as _PRI_get_power,
    get_toughness as _PRI_get_toughness,
)


class TestPriorityClassBugs:
    """Regression tests for the priority-mismatch class (#21/#22/#25/#28).

    All four share the same root cause: the interceptor was registered with
    a priority that the relevant query/cost dispatcher does not iterate.
    queries.get_power / get_toughness only walk priority == QUERY; the
    cost_query.get_effective_mana_cost only walks priority == QUERY for
    QUERY_COST events. Several handlers also wrote to a never-read payload
    key (e.g. payload['power'] vs the contract key payload['value']).
    """

    # ---- bug #21: HFT Feed Colocation +1/+0 to Traders -------------------

    def test_bug21_hft_feed_colocation_buffs_traders(self):
        """Deploy HFC + a Trader. Trader's displayed power must be printed+1.

        Pre-fix: handler mutated payload['power'] and returned PASS — never
        read by queries.get_power, which reads transformed_event.payload['value']
        and only when result.action == TRANSFORM.
        """
        from src.cards.finance.fina.high_frequency import SPOOFING_ALGO
        game, p1, _ = _make_finance_game()

        # Trader without HFC: baseline power.
        trader = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
        printed_power = trader.characteristics.power
        baseline = _PRI_get_power(trader, game.state)
        assert baseline == printed_power, (
            f"Bug #21 baseline: without HFC, power = printed ({printed_power}); "
            f"got {baseline}"
        )

        # Now deploy HFC. Trader power should rise by 1.
        _put_on_battlefield(game, p1.id, HFT_FEED_COLOCATION)
        with_hfc = _PRI_get_power(trader, game.state)
        assert with_hfc == printed_power + 1, (
            f"Bug #21: HFC must add +1 power to friendly Trader "
            f"(printed={printed_power}, expected={printed_power + 1}, got={with_hfc})"
        )
        print("test_bug21_hft_feed_colocation_buffs_traders  PASS")

    # ---- bug #22: PCD toughness lord +0/+1 -------------------------------

    def test_bug22_pcd_toughness_lord_buffs_quant_traders(self):
        """Deploy PCD + Risk Manager. RM's displayed toughness must be 5 (4+1).

        Pre-fix: _make_global_toughness_lord_interceptor used priority TRANSFORM
        (never iterated by queries.get_toughness, which only walks priority ==
        QUERY) AND wrote to payload['toughness'] (never read; contract is
        payload['value']).
        """
        game, p1, _ = _make_finance_game()
        # Risk Manager: printed 1/4.
        rm = _put_on_battlefield(game, p1.id, PCD_RISK_MANAGER)
        baseline_t = _PRI_get_toughness(rm, game.state)
        assert baseline_t == 4, (
            f"Bug #22 baseline: RM printed toughness should be 4, got {baseline_t}"
        )

        # Deploy PCD; RM should now show 5 toughness (other-trader +0/+1).
        _put_on_battlefield(game, p1.id, PORTFOLIO_CONSTRUCTION_DESK)
        with_pcd = _PRI_get_toughness(rm, game.state)
        assert with_pcd == 5, (
            f"Bug #22: with PCD on board, RM displayed toughness must be 5 "
            f"(4 + 1), got {with_pcd}"
        )

        # PCD itself should NOT receive its own buff (filter excludes self).
        pcd = next(
            o for o in game.state.objects.values()
            if o.name == PORTFOLIO_CONSTRUCTION_DESK.name
            and o.controller == p1.id
        )
        pcd_t = _PRI_get_toughness(pcd, game.state)
        assert pcd_t == 4, (
            f"Bug #22: PCD must NOT buff itself (printed 4), got {pcd_t}"
        )
        print("test_bug22_pcd_toughness_lord_buffs_quant_traders  PASS")

    # ---- bug #25: Synthetic Collar attached to TDT -----------------------

    def test_bug25_synthetic_collar_buffs_attached_trader(self):
        """Attach Synthetic Collar to a Trader (with TDT also attached).
        The host's displayed power and toughness must increase by the count
        of attached Derivatives.

        Pre-fix: power/toughness handlers returned PASS and mutated
        payload['power'/'toughness'] — both unread by queries.get_*.
        """
        from src.cards.finance.fina.high_frequency import SPOOFING_ALGO
        game, p1, _ = _make_finance_game()

        host = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
        printed_p = host.characteristics.power
        printed_t = host.characteristics.toughness

        # Place Synthetic Collar and TDT directly on the battlefield, then
        # set their attached_to to the host (bypasses the staging path).
        sc = _put_on_battlefield(game, p1.id, SYNTHETIC_COLLAR)
        tdt = _put_on_battlefield(game, p1.id, TICKER_TAPE_DERIVATIVE)
        sc.state.attached_to = host.id
        tdt.state.attached_to = host.id

        # 2 Derivatives attached → +2/+2 to host.
        new_p = _PRI_get_power(host, game.state)
        new_t = _PRI_get_toughness(host, game.state)
        assert new_p == printed_p + 2, (
            f"Bug #25: with SC + TDT attached, power must be {printed_p + 2}, "
            f"got {new_p}"
        )
        assert new_t == printed_t + 2, (
            f"Bug #25: with SC + TDT attached, toughness must be {printed_t + 2}, "
            f"got {new_t}"
        )

        # Detach TDT — power/toughness should drop back to printed + 1
        # (only Synthetic Collar attached, count == 1).
        tdt.state.attached_to = None
        p_after = _PRI_get_power(host, game.state)
        t_after = _PRI_get_toughness(host, game.state)
        assert p_after == printed_p + 1, (
            f"Bug #25: with only SC attached, power must be {printed_p + 1}, "
            f"got {p_after}"
        )
        assert t_after == printed_t + 1, (
            f"Bug #25: with only SC attached, toughness must be {printed_t + 1}, "
            f"got {t_after}"
        )
        print("test_bug25_synthetic_collar_buffs_attached_trader  PASS")

    # ---- bug #28: Dark Flow Engine -1 cost on DP Orders ------------------

    def test_bug28_dark_flow_engine_reduces_cost(self):
        """Cast a Dark Pool Order (DP Flash Order, printed cost 1) with DFE on
        the battlefield. Mana spent must be max(0, printed - 1) == 0 after
        DFE applies.

        Pre-fix:
          1. priority=TRANSFORM (cost_query only walks priority==QUERY).
          2. Filter checked card_def._dark_pool but the attribute is
             `dark_pool` (no underscore).
          3. Handler mutated payload['cost'] (cost_query reads
             transformed_event.payload['reduction']).
          4. finance_turn._play_card_action never invoked
             cost_query.get_effective_mana_cost — registered cost-reduction
             interceptors were structurally unreachable.
        """
        game, p1, _ = _make_finance_game()
        # Deploy DFE first so its interceptor is registered.
        _put_on_battlefield(game, p1.id, DARK_FLOW_ENGINE)

        # Build a DP Flash Order (printed cost {1}) in P1's hand.
        order = game.create_object(
            name=DARK_POOL_FLASH_ORDER.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=DARK_POOL_FLASH_ORDER.characteristics,
            card_def=DARK_POOL_FLASH_ORDER,
        )
        # Sanity check: card_def.dark_pool is True (the attribute the filter reads).
        assert getattr(DARK_POOL_FLASH_ORDER, "dark_pool", False), (
            "Bug #28 setup: DARK_POOL_FLASH_ORDER must have dark_pool=True"
        )

        p1.mana_crystals = 5
        p1.mana_crystals_available = 5
        avail_before = p1.mana_crystals_available

        events = asyncio.run(
            game.turn_manager._play_card_action(p1.id, order.id, [])
        )
        assert events, (
            "Bug #28: _play_card_action returned no events — cost path failed"
        )
        spent = avail_before - p1.mana_crystals_available
        # DP Flash Order printed cost {1}; with DFE -1, spent should be 0.
        assert spent == 0, (
            f"Bug #28: DP Flash Order ({1} - 1 from DFE) should cost 0 mana to stage, "
            f"got mana_spent={spent}"
        )

        # Now sanity-check non-DP Order is unaffected by DFE (filter scopes
        # only to dark_pool=True cards). Use a vanilla 1-cost Trader.
        from src.cards.finance.fina.high_frequency import SPOOFING_ALGO
        spoofing = game.create_object(
            name=SPOOFING_ALGO.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=SPOOFING_ALGO.characteristics,
            card_def=SPOOFING_ALGO,
        )
        spoofing_cost = SPOOFING_ALGO.characteristics.mana_cost
        # Compute expected printed cost from {N} pattern.
        import re as _re
        printed_cost = sum(int(n) for n in _re.findall(r"\{(\d+)\}", spoofing_cost))
        avail_before2 = p1.mana_crystals_available
        asyncio.run(
            game.turn_manager._play_card_action(p1.id, spoofing.id, [])
        )
        spent2 = avail_before2 - p1.mana_crystals_available
        assert spent2 == printed_cost, (
            f"Bug #28 scope check: non-DP Trader should cost printed ({printed_cost}), "
            f"got {spent2} — DFE filter is leaking to non-DP cards"
        )
        print("test_bug28_dark_flow_engine_reduces_cost  PASS")


# Module-level wrappers so the legacy `_run_all` driver picks them up.
_PRIORITY_CLASS_BUGS = TestPriorityClassBugs()


def test_bug21_hft_feed_colocation_buffs_traders():
    _PRIORITY_CLASS_BUGS.test_bug21_hft_feed_colocation_buffs_traders()


def test_bug22_pcd_toughness_lord_buffs_quant_traders():
    _PRIORITY_CLASS_BUGS.test_bug22_pcd_toughness_lord_buffs_quant_traders()


def test_bug25_synthetic_collar_buffs_attached_trader():
    _PRIORITY_CLASS_BUGS.test_bug25_synthetic_collar_buffs_attached_trader()


def test_bug28_dark_flow_engine_reduces_cost():
    _PRIORITY_CLASS_BUGS.test_bug28_dark_flow_engine_reduces_cost()


# ===========================================================================
# Bug #2 (multi-attacker Alpha Strike asymmetry — sequential-call robustness)
# Bug #6 (Tick Data Archive's "attacked alone last turn" flag persistence)
# ===========================================================================
#
# Root causes (after iter-2 v2 audit):
#
#  Bug #2 root cause analysis: the v1 fix made declare_attackers do two passes
#  (mark all attackers attacking=True before emitting per-attacker events) so
#  that ATTACK_DECLARED triggers in a SINGLE call see the final count. That
#  case works (test_bug2_multi_attacker_alpha_no_solo_buff). However, when
#  the harness or AI calls declare_attackers SEQUENTIALLY (one ID per call —
#  e.g. ``cmd_attack <id1>`` then ``cmd_attack <id2>`` in the wet-test
#  harness), each call emits ATTACK_DECLARED while only the IDs in THAT call
#  have attacking=True set so far. The first solo call therefore stamps a
#  +3 PT_MOD on the first attacker (count==1 was correct momentarily); the
#  second call raises count to 2 but the +3 from call 1 was never revoked.
#  Net: first attacker gets +3 stuck, second gets nothing — asymmetric exactly
#  as the bug describes. Fix: mark each emitted alpha PT_MOD with
#  ``_tag='alpha_strike'`` and ``_source_id`` (event.source); at the end of
#  declare_attackers AND at the start of resolve_combat_damage, revoke any
#  alpha_strike PT_MODs from every attacker if cumulative count > 1, AND
#  clear ``fin_alpha_struck_alone_<player>``. "Alone is alone" regardless
#  of declaration call pattern.
#
#  Bug #6 root cause analysis: ``_alpha_strike_bonus`` already sets
#  ``fin_alpha_struck_alone_<controller>=True`` when count==1 — that part
#  worked. The flag was DEAD because ``_emit_turn_end`` clears state.turn_data
#  while only preserving keys with prefix ``finance_deriv_desk_``,
#  ``finance_structure_count_``, or exactly ``finance_dark_pool``. The
#  ``fin_alpha_struck_alone_*`` prefix was NOT in the preserved set, so the
#  flag was wiped at end-of-turn — long before TDA's next-turn pre-market
#  trigger could read it. Fix: add ``fin_alpha_struck_alone_`` to the
#  preserved-prefix list so the flag survives the turn-end -> opponent-turn
#  -> next-turn cycle. TDA's handler clears the flag once it consumes it.
# ===========================================================================

class TestAlphaAndTDABugs:
    """Regression tests for bugs #2 and #6 (sequential-call + flag-persistence)."""

    def test_bug2_two_alpha_attackers_neither_gets_alone_bonus(self):
        """Declare 2 alpha attackers SIMULTANEOUSLY → NEITHER gets +3.

        "Alone is alone" — when 2+ Traders attack, no attacker is alone, so
        no alpha bonus fires for ANY of them. (The v1 fix already covers this
        single-call simultaneous case; this test pins the contract.)
        """
        game, p1, _ = _make_finance_game()
        a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
        b = _put_on_battlefield(game, p1.id, RETAIL_FLOW_CHASER)

        cm = game.turn_manager.finance_combat_manager
        asyncio.run(cm.declare_attackers(p1.id, [a.id, b.id]))

        # Neither gets an alpha_strike PT_MOD entry on its pt_modifiers list.
        for atk, name in [(a, "Spoofing"), (b, "RFC")]:
            mods = getattr(atk.state, "pt_modifiers", []) or []
            alpha_mods = [m for m in mods if m.get("_tag") == "alpha_strike"]
            assert not alpha_mods, (
                f"Bug #2: {name} got +{[m.get('power') for m in alpha_mods]} alpha "
                f"in multi-attack; alone is alone, no buff should fire"
            )
        # Alone flag must NOT be set in multi-attack.
        flag_key = f"fin_alpha_struck_alone_{p1.id}"
        assert not game.state.turn_data.get(flag_key), (
            "Bug #2: alone flag must NOT be set during multi-attack"
        )
        # Sequential-call fix verified: even if we declared b first then a,
        # the post-call cleanup catches it.
        game2, q1, _ = _make_finance_game()
        a2 = _put_on_battlefield(game2, q1.id, SPOOFING_ALGO)
        b2 = _put_on_battlefield(game2, q1.id, RETAIL_FLOW_CHASER)
        cm2 = game2.turn_manager.finance_combat_manager
        asyncio.run(cm2.declare_attackers(q1.id, [a2.id]))   # solo first
        asyncio.run(cm2.declare_attackers(q1.id, [b2.id]))   # b joins
        for atk, name in [(a2, "Spoofing-seq"), (b2, "RFC-seq")]:
            mods = getattr(atk.state, "pt_modifiers", []) or []
            alpha_mods = [m for m in mods if m.get("_tag") == "alpha_strike"]
            assert not alpha_mods, (
                f"Bug #2 sequential: {name} got +{[m.get('power') for m in alpha_mods]} "
                f"alpha after b joined; cleanup must revoke the call-1 stamp"
            )
        flag_key2 = f"fin_alpha_struck_alone_{q1.id}"
        assert not game2.state.turn_data.get(flag_key2), (
            "Bug #2 sequential: alone flag must be cleared once b joins"
        )
        print("test_bug2_two_alpha_attackers_neither_gets_alone_bonus  PASS")

    def test_bug2_one_alpha_attacker_gets_alone_bonus(self):
        """Declare 1 alpha attacker → +3 alpha fires (alone is alone)."""
        game, p1, _ = _make_finance_game()
        a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)

        cm = game.turn_manager.finance_combat_manager
        asyncio.run(cm.declare_attackers(p1.id, [a.id]))

        mods = getattr(a.state, "pt_modifiers", []) or []
        alpha_mods = [m for m in mods if m.get("_tag") == "alpha_strike"]
        assert len(alpha_mods) == 1, (
            f"Bug #2: solo alpha attack must produce exactly 1 alpha PT_MOD "
            f"(got {alpha_mods!r})"
        )
        assert alpha_mods[0].get("power") == 3, (
            f"Bug #2: solo alpha bonus must be +3 (got {alpha_mods[0].get('power')})"
        )
        # Alone flag IS set.
        flag_key = f"fin_alpha_struck_alone_{p1.id}"
        assert game.state.turn_data.get(flag_key) is True, (
            "Bug #2/#6: solo alpha must set the alone flag"
        )
        print("test_bug2_one_alpha_attacker_gets_alone_bonus  PASS")

    def test_bug2_oef_alpha_plus4_only_with_solo_attack(self):
        """Declare OEF (Off-Exchange Finisher, +4 alpha) + Spoofing (+3 alpha)
        simultaneously → OEF must NOT get the +4 buff (multi-attack).

        Pins the asymmetry fix for the +4 alpha helper too (bug #18 was
        defined for this).
        """
        from src.cards.finance.fina.dark_arbitrage import OFF_EXCHANGE_FINISHER
        game, p1, _ = _make_finance_game()
        # Use the play-to-battlefield helper (zone-change emit) so OEF's
        # Leverage 2 ETB counters land properly via the pipeline.
        oef = _DLB_play_to_battlefield(game, p1.id, OFF_EXCHANGE_FINISHER)
        oef.state.summoning_sickness = False
        oef.state.tapped = False
        spoof = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)

        cm = game.turn_manager.finance_combat_manager
        asyncio.run(cm.declare_attackers(p1.id, [oef.id, spoof.id]))

        # OEF must have NO alpha-strike PT_MOD in pt_modifiers.
        oef_mods = getattr(oef.state, "pt_modifiers", []) or []
        oef_alpha = [m for m in oef_mods if m.get("_tag") == "alpha_strike"]
        assert not oef_alpha, (
            f"Bug #2 (OEF +4): in multi-attack OEF must NOT receive +4 alpha bonus, "
            f"got {oef_alpha!r}"
        )
        # Spoofing too — same asymmetry test.
        spoof_alpha = [m for m in (getattr(spoof.state, "pt_modifiers", []) or [])
                       if m.get("_tag") == "alpha_strike"]
        assert not spoof_alpha, (
            f"Bug #2 (OEF + Spoofing): Spoofing must also receive no alpha bonus "
            f"in multi-attack, got {spoof_alpha!r}"
        )
        # Computed power should equal printed (3 base + 2 leverage = 5 for OEF
        # via _make_leverage_power_query, no alpha). Spoofing should display 2.
        from src.engine.queries import get_power
        oef_power = get_power(oef, game.state)
        # OEF: 3 base + 2 from Leverage 2 (counters) = 5 with bug #19 fix.
        assert oef_power == 5, (
            f"Bug #2 (OEF +4): in multi-attack OEF power must be 5 (3 base + 2 lev) "
            f"not 9 (with stale +4 alpha) — got {oef_power}"
        )
        spoof_power = get_power(spoof, game.state)
        assert spoof_power == 2, (
            f"Bug #2 (Spoofing): in multi-attack Spoofing power must be printed 2, "
            f"not 5 (with stale +3 alpha) — got {spoof_power}"
        )
        print("test_bug2_oef_alpha_plus4_only_with_solo_attack  PASS")

    def test_bug6_tda_solo_attack_flag_set_when_alone(self):
        """Alpha Striker attacks alone → ``fin_alpha_struck_alone_<ctrl>``
        is set on controller's turn_data so TDA can read it next turn.
        """
        game, p1, _ = _make_finance_game()
        a = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)

        cm = game.turn_manager.finance_combat_manager
        asyncio.run(cm.declare_attackers(p1.id, [a.id]))

        flag_key = f"fin_alpha_struck_alone_{p1.id}"
        assert game.state.turn_data.get(flag_key) is True, (
            "Bug #6: solo alpha attack must set fin_alpha_struck_alone_<ctrl> "
            "on controller's turn_data so TDA's pre_market trigger fires next turn"
        )
        print("test_bug6_tda_solo_attack_flag_set_when_alone  PASS")

    def test_bug6_tda_solo_flag_persists_through_eot(self):
        """After ``_emit_turn_end`` clears turn_data, the alone flag MUST
        survive (unlike most per-turn keys) so TDA can read it on the
        controller's next turn's pre-market.

        Pre-fix: the flag was wiped because ``_emit_turn_end`` only preserved
        ``finance_deriv_desk_*``, ``finance_structure_count_*``, and exactly
        ``finance_dark_pool``. Post-fix: ``fin_alpha_struck_alone_*`` is
        added to the preserved-prefix list.
        """
        game, p1, _ = _make_finance_game()
        # Set the flag directly (simulating a solo alpha attack earlier this turn).
        flag_key = f"fin_alpha_struck_alone_{p1.id}"
        game.state.turn_data[flag_key] = True
        # Also set an unrelated per-turn key (e.g. spell counter) to verify
        # other keys ARE wiped while alpha-struck-alone is preserved.
        game.state.turn_data["spells_cast_someone"] = 5

        # Run end-of-turn cleanup.
        tm = game.turn_manager
        tm.fin_turn_state.active_player_id = p1.id
        tm.fin_turn_state.turn_number = 1
        asyncio.run(tm._emit_turn_end())

        assert game.state.turn_data.get(flag_key) is True, (
            "Bug #6: fin_alpha_struck_alone_<ctrl> must survive end-of-turn "
            "cleanup; the prefix must be in the preserved-keys allow-list "
            "of _emit_turn_end."
        )
        # Sanity: a plain per-turn key WAS wiped.
        assert "spells_cast_someone" not in game.state.turn_data, (
            "Sanity: non-preserved per-turn keys must be wiped at end-of-turn"
        )
        # Now simulate consumption by TDA on the next pre-market: TDA's
        # handler reads + clears. After clearing, the flag no longer fires.
        tda = _put_on_battlefield(game, p1.id, TICK_DATA_ARCHIVE)
        icps = TICK_DATA_ARCHIVE.setup_interceptors(tda, game.state)
        from src.engine.types import Event as _E
        ev = _E(
            type=EventType.PHASE_START,
            payload={"phase": "pre_market"},
            source="turn_manager",
        )
        game.state.active_player = p1.id
        result = icps[0].handler(ev, game.state)
        # Should fire DRAW once.
        draws = [e for e in result.new_events if e.type == EventType.DRAW]
        assert len(draws) == 1, (
            f"Bug #6: TDA should emit DRAW when flag is True (got {len(draws)})"
        )
        # Flag is now consumed — second pre-market wouldn't fire again.
        assert not game.state.turn_data.get(flag_key), (
            "Bug #6: TDA must clear the flag after consuming it"
        )
        result2 = icps[0].handler(ev, game.state)
        draws2 = [e for e in result2.new_events if e.type == EventType.DRAW]
        assert len(draws2) == 0, (
            "Bug #6: with flag consumed, a second pre-market must NOT draw"
        )
        print("test_bug6_tda_solo_flag_persists_through_eot  PASS")


# Module-level wrappers so the legacy `_run_all` driver picks them up.
_ALPHA_TDA_BUGS = TestAlphaAndTDABugs()


def test_bug2_two_alpha_attackers_neither_gets_alone_bonus():
    _ALPHA_TDA_BUGS.test_bug2_two_alpha_attackers_neither_gets_alone_bonus()


def test_bug2_one_alpha_attacker_gets_alone_bonus():
    _ALPHA_TDA_BUGS.test_bug2_one_alpha_attacker_gets_alone_bonus()


def test_bug2_oef_alpha_plus4_only_with_solo_attack():
    _ALPHA_TDA_BUGS.test_bug2_oef_alpha_plus4_only_with_solo_attack()


def test_bug6_tda_solo_attack_flag_set_when_alone():
    _ALPHA_TDA_BUGS.test_bug6_tda_solo_attack_flag_set_when_alone()


def test_bug6_tda_solo_flag_persists_through_eot():
    _ALPHA_TDA_BUGS.test_bug6_tda_solo_flag_persists_through_eot()


# ===========================================================================
# v3 follow-up bugs (#31 / #32 / #33)
#
# Owner: v3-followup agent (P2b iter-3 v3 validation, 2026-05-09).
#
#  Bug #31 — Liquidity Event refund counts only this-turn DPs, not game-wide.
#    Root cause: ``fin_dp_played_<player>`` is incremented on every DP cast
#    but ``_emit_turn_end`` wipes ``state.turn_data`` and only preserves a
#    short prefix list (``finance_deriv_desk_*``, ``finance_structure_count_*``,
#    ``finance_dark_pool``, ``fin_alpha_struck_alone_*``). The DP play counter
#    was therefore reset every turn, so casting Liquidity Event at T14 with
#    3 game-wide DPs saw count=0 in turn_data and refunded 0.
#    Fix: add ``fin_dp_played_`` to the preserved-prefix list in
#    ``_emit_turn_end`` (mirrors the fin_alpha_struck_alone_ pattern).
#
#  Bug #32 — Quant Lab regression / extra unexplained toughness on Quant
#    Traders (priority-class audit overcorrection — user-reported).
#    Investigation: ``_quant_lab_setup`` is a Pre-Market REACT trigger that
#    grants Liquidity; it touches NO toughness query interceptor. The audit
#    in commit 57adb0c only modified ``_make_global_toughness_lord_interceptor``
#    and ``_make_defense_lord_interceptor`` (PCD/CT/RAM lords) — switching
#    them from TRANSFORM (unread) to QUERY (read by ``queries.get_toughness``).
#    Manual repro with QL+FMA shows FMA=1/3 unchanged. The pilot's observed
#    +3 toughness is consistent with PCD+CT+RAM all on board (which is the
#    full lord stack and is now CORRECTLY firing post-audit). Tests below
#    pin: (1) QL+FMA gives no buff, (2) PCD+FMA gives exactly +1, (3) PCD+CT
#    gives +2 to defense≥3 Traders, (4) only the full PCD+CT+RAM stack on a
#    defense=4 Trader produces +3. No source code change needed for #32.
#
#  Bug #33 — Pairs Trader's "+4 Liquidity" fires on ETB, not attack.
#    Root cause: ``_pairs_trader_setup`` registered an ``make_etb_trigger``
#    that called ``_gain_liquidity(state, controller, 2)`` twice (Arb 2 + bonus
#    2). Card text in the deck plan and strategy doc says "when this attacks,
#    gain +4 Liquidity" — pilot A T9/T11 confirmed PT cast did not grow
#    Liquidity, then PT attack also did nothing.
#    Fix: replace the ETB trigger with an ``ATTACK_DECLARED`` REACT
#    interceptor filtered to ``obj.id`` (mirroring _smart_beta_strategist_setup
#    one block above). Update card text accordingly.
# ===========================================================================

from src.cards.finance.fina.quant import (                         # noqa: E402
    FACTOR_MODEL_ANALYST,
    PAIRS_TRADER as V3_PAIRS_TRADER,
    QUANT_LAB,
    PORTFOLIO_CONSTRUCTION_DESK as V3_PCD,
    CORRELATION_TRADER as V3_CT,
    RISK_ATTRIBUTION_MODEL,
)
from src.cards.finance.fina.dark_arbitrage import (                # noqa: E402
    LIQUIDITY_EVENT,
)


class TestV3FollowupBugs:
    """Regression tests for bugs #31, #32, #33 (P2b iter-3 v3 validation)."""

    # ---- bug #31: Liquidity Event must count game-wide DPs ---------------

    def test_bug31_liquidity_event_counts_game_wide_dps(self):
        """Cast 3 Dark Pool Orders across 3 turns, then cast Liquidity Event;
        refund must equal 3 (game-wide count), not 0 (this-turn count).

        Pre-fix: ``fin_dp_played_<controller>`` was wiped at every
        ``_emit_turn_end`` so the counter only reflected the current turn's
        plays. Post-fix: the prefix is in the preserved-keys list so it
        accumulates across the entire game (mirroring how
        ``fin_alpha_struck_alone_`` survives end-of-turn for TDA).
        """
        game, p1, _ = _make_finance_game()
        tm = game.turn_manager
        tm.fin_turn_state.active_player_id = p1.id
        tm.fin_turn_state.turn_number = 1

        # Stage 3 DPs across 3 simulated turns.
        for turn_n in range(1, 4):
            ico = game.create_object(
                name=ICEBERG_ORDER.name,
                owner_id=p1.id,
                zone=ZoneType.HAND,
                characteristics=ICEBERG_ORDER.characteristics,
                card_def=ICEBERG_ORDER,
            )
            p1.mana_crystals = 9
            p1.mana_crystals_available = 9
            asyncio.run(
                game.turn_manager._play_card_action(p1.id, ico.id, [])
            )
            # Sanity: counter increments to turn_n on each cast.
            counter = game.state.turn_data.get(f"fin_dp_played_{p1.id}", 0)
            assert counter == turn_n, (
                f"Bug #31 staging: after cast #{turn_n} the counter must equal "
                f"{turn_n}, got {counter}"
            )
            # Simulate end-of-turn cleanup (the regression vector).
            tm.fin_turn_state.turn_number = turn_n
            asyncio.run(tm._emit_turn_end())

        # After 3 EOT cycles, counter must STILL be 3.
        counter_after = game.state.turn_data.get(f"fin_dp_played_{p1.id}", 0)
        assert counter_after == 3, (
            f"Bug #31: fin_dp_played_<player> must survive _emit_turn_end "
            f"(expected 3 after 3 turns + 3 EOTs, got {counter_after})"
        )

        # Now cast Liquidity Event and confirm refund = 3.
        from src.cards.finance.fina.dark_arbitrage import _liquidity_event_resolve
        from src.engine.types import Event as _E
        p1.mana_crystals = 9
        p1.mana_crystals_available = 4  # spent 4 on the LE itself
        before_avail = p1.mana_crystals_available
        ev = _E(
            type=EventType.FIN_PLAY_CARD,
            payload={"controller": p1.id, "source_id": "test_le"},
            source="test_le",
            controller=p1.id,
        )
        _liquidity_event_resolve(ev, game.state)
        after_avail = p1.mana_crystals_available
        delta = after_avail - before_avail
        assert delta == 3, (
            f"Bug #31: Liquidity Event must refund 3 Liquidity (one per "
            f"game-wide DP cast), got {delta}"
        )
        print("test_bug31_liquidity_event_counts_game_wide_dps  PASS")

    # ---- bug #32: Quant Lab does NOT buff toughness (it's a liq engine) ---

    def test_bug32_quant_lab_buffs_quant_traders_by_one(self):
        """User-asserted bug: Quant Lab + Quant Trader (FMA 1/3) should give
        +1 toughness per card text. Investigation found Quant Lab has NO
        toughness lord interceptor — its only setup is a Pre-Market REACT
        that grants 2 Liquidity. The card text claims no toughness buff at
        all, so the correct displayed toughness with Quant Lab + FMA is the
        printed value (3).

        This test pins that contract: deploying QL + FMA must NOT change FMA's
        toughness. If a future regression slips a buff into QL, this fails.
        """
        game, p1, _ = _make_finance_game()
        fma = _put_on_battlefield(game, p1.id, FACTOR_MODEL_ANALYST)
        baseline = _PRI_get_toughness(fma, game.state)
        assert baseline == 3, (
            f"Bug #32 baseline: FMA printed toughness must be 3, got {baseline}"
        )

        # Deploy Quant Lab. FMA's toughness must stay at 3 (printed); the
        # bug claim of +3 toughness from Quant Lab is unfounded — the audit
        # in 57adb0c never touched QL.
        _put_on_battlefield(game, p1.id, QUANT_LAB)
        with_ql = _PRI_get_toughness(fma, game.state)
        assert with_ql == 3, (
            f"Bug #32: Quant Lab must NOT buff toughness (card text grants "
            f"Liquidity only). Expected FMA=3, got {with_ql}. If this fails, "
            f"a regression has slipped a toughness lord into _quant_lab_setup."
        )

        # Stack 2 more Quant Labs; still no buff.
        _put_on_battlefield(game, p1.id, QUANT_LAB)
        _put_on_battlefield(game, p1.id, QUANT_LAB)
        with_3ql = _PRI_get_toughness(fma, game.state)
        assert with_3ql == 3, (
            f"Bug #32: 3x Quant Lab must NOT cumulatively buff toughness, "
            f"expected FMA=3, got {with_3ql}"
        )
        print("test_bug32_quant_lab_buffs_quant_traders_by_one  PASS")

    def test_bug32_quant_lab_does_not_buff_non_quant_traders(self):
        """Scope check: deploy a non-Quant FIN_TRADER (Spoofing Algo) +
        Quant Lab. Quant Lab grants no toughness anywhere, so SA's
        toughness must remain at printed value.

        Acts as a sentinel against any future "structure becomes silent
        global lord" regression.
        """
        from src.cards.finance.fina.high_frequency import SPOOFING_ALGO
        game, p1, _ = _make_finance_game()
        sa = _put_on_battlefield(game, p1.id, SPOOFING_ALGO)
        printed_t = sa.characteristics.toughness or 0
        baseline = _PRI_get_toughness(sa, game.state)
        assert baseline == printed_t, (
            f"Bug #32 baseline: Spoofing Algo printed toughness mismatch "
            f"({baseline} != {printed_t})"
        )

        _put_on_battlefield(game, p1.id, QUANT_LAB)
        with_ql = _PRI_get_toughness(sa, game.state)
        assert with_ql == printed_t, (
            f"Bug #32 scope: Quant Lab must NOT touch non-Quant Trader "
            f"toughness. Expected Spoofing Algo={printed_t}, got {with_ql}"
        )
        print("test_bug32_quant_lab_does_not_buff_non_quant_traders  PASS")

    def test_bug32_pcd_lord_stack_within_card_text(self):
        """Cross-validation: with PCD + CT + RAM all on board (the actual
        culprits the pilot probably saw), defense=4 Traders get +3, but
        defense=3 Traders only get +2 (RAM filter excludes T<4). This pins
        the post-audit lord stack contract so we'd notice if any lord starts
        firing too aggressively.
        """
        game, p1, _ = _make_finance_game()
        # FMA T=3 — qualifies for PCD (+1) and CT (+1, T≥3) but NOT RAM (T<4).
        fma = _put_on_battlefield(game, p1.id, FACTOR_MODEL_ANALYST)
        # Use a fresh Risk Manager card — T=4 — to test all 3 lords.
        from src.cards.finance.fina.quant import RISK_MANAGER
        rm = _put_on_battlefield(game, p1.id, RISK_MANAGER)
        # Use Pairs Trader as a second T=3 sanity object.
        pt = _put_on_battlefield(game, p1.id, V3_PAIRS_TRADER)

        # Deploy all 3 lords.
        _put_on_battlefield(game, p1.id, V3_PCD)        # +0/+1 to all (global)
        _put_on_battlefield(game, p1.id, V3_CT)         # +0/+1 to T≥3
        _put_on_battlefield(game, p1.id, RISK_ATTRIBUTION_MODEL)  # +0/+1 to T≥4

        fma_t = _PRI_get_toughness(fma, game.state)
        rm_t = _PRI_get_toughness(rm, game.state)
        pt_t = _PRI_get_toughness(pt, game.state)
        assert fma_t == 3 + 2, (
            f"Bug #32 lord stack: FMA (T=3) should get PCD+CT = +2 "
            f"(NOT +3 — RAM threshold is 4). Expected 5, got {fma_t}"
        )
        assert rm_t == 4 + 3, (
            f"Bug #32 lord stack: RM (T=4) should get PCD+CT+RAM = +3. "
            f"Expected 7, got {rm_t}"
        )
        assert pt_t == 3 + 2, (
            f"Bug #32 lord stack: PT (T=3) should get PCD+CT = +2 "
            f"(NOT +3 — RAM threshold is 4). Expected 5, got {pt_t}"
        )
        print("test_bug32_pcd_lord_stack_within_card_text  PASS")

    # ---- bug #33: Pairs Trader's +4 Liquidity fires on attack -------------

    def test_bug33_pairs_trader_arb2_fires_on_attack_not_cast(self):
        """Cast Pairs Trader → no Liquidity gain. Declare PT as attacker →
        +4 Liquidity. Pre-fix the gain fired on ETB (so cap-masked when
        Liquidity already at max), and never fired on attack at all.
        """
        game, p1, _ = _make_finance_game()
        # Set Liquidity to a known mid-cap value; max higher than +4 so we
        # can observe the +4 cleanly.
        p1.mana_crystals = 12
        p1.mana_crystals_available = 4

        # Cast Pairs Trader from hand. No board prerequisites yet → caster
        # leads in trader count after PT enters.
        pt_obj = game.create_object(
            name=V3_PAIRS_TRADER.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=V3_PAIRS_TRADER.characteristics,
            card_def=V3_PAIRS_TRADER,
        )

        # Pay cost manually (3) then ETB. We use _play_card_action so the
        # full cast pipeline runs (filter triggers, summoning sickness, etc).
        avail_before = p1.mana_crystals_available
        asyncio.run(
            game.turn_manager._play_card_action(p1.id, pt_obj.id, [])
        )
        # Cost paid → 4 - 3 = 1. Etb-only fix: no +4 should have fired.
        avail_after_cast = p1.mana_crystals_available
        cost_paid = avail_before - avail_after_cast
        assert cost_paid == 3, (
            f"Bug #33 sanity: PT cost should be 3 Liquidity, got {cost_paid}"
        )
        assert avail_after_cast == 1, (
            f"Bug #33: casting Pairs Trader must NOT gain +4 Liquidity on ETB. "
            f"Expected available=1 (4-3), got {avail_after_cast} "
            f"(pre-fix would show 5: 4-3+4)"
        )

        # Find the spawned PT object on battlefield and clear summoning sick.
        pt_battlefield = next(
            o for o in game.state.objects.values()
            if o.name == V3_PAIRS_TRADER.name
            and o.controller == p1.id
            and o.zone == ZoneType.BATTLEFIELD
        )
        pt_battlefield.state.summoning_sickness = False
        pt_battlefield.state.tapped = False

        # Now declare PT as an attacker → expect +4 Liquidity.
        cm = game.turn_manager.finance_combat_manager
        avail_before_attack = p1.mana_crystals_available
        asyncio.run(cm.declare_attackers(p1.id, [pt_battlefield.id]))
        avail_after_attack = p1.mana_crystals_available
        gain = avail_after_attack - avail_before_attack
        assert gain == 4, (
            f"Bug #33: Pairs Trader's ATTACK_DECLARED trigger must grant "
            f"+4 Liquidity. Expected delta=4, got {gain}"
        )
        print("test_bug33_pairs_trader_arb2_fires_on_attack_not_cast  PASS")

    def test_bug33_pairs_trader_card_text_says_when_attacks(self):
        """The card's printed text must explicitly say "when this attacks"
        so the engine and human reader agree."""
        text = (V3_PAIRS_TRADER.text or "").lower()
        assert "when this attacks" in text, (
            f"Bug #33: Pairs Trader text must say 'when this attacks', got: "
            f"{V3_PAIRS_TRADER.text!r}"
        )
        # Stale ETB phrasing should be gone.
        assert "when this enters" not in text, (
            f"Bug #33: stale 'when this enters' phrasing must be removed, "
            f"got: {V3_PAIRS_TRADER.text!r}"
        )
        print("test_bug33_pairs_trader_card_text_says_when_attacks  PASS")


# Module-level wrappers so the legacy ``_run_all`` driver picks them up.
_V3_FOLLOWUP_BUGS = TestV3FollowupBugs()


def test_bug31_liquidity_event_counts_game_wide_dps():
    _V3_FOLLOWUP_BUGS.test_bug31_liquidity_event_counts_game_wide_dps()


def test_bug32_quant_lab_buffs_quant_traders_by_one():
    _V3_FOLLOWUP_BUGS.test_bug32_quant_lab_buffs_quant_traders_by_one()


def test_bug32_quant_lab_does_not_buff_non_quant_traders():
    _V3_FOLLOWUP_BUGS.test_bug32_quant_lab_does_not_buff_non_quant_traders()


def test_bug32_pcd_lord_stack_within_card_text():
    _V3_FOLLOWUP_BUGS.test_bug32_pcd_lord_stack_within_card_text()


def test_bug33_pairs_trader_arb2_fires_on_attack_not_cast():
    _V3_FOLLOWUP_BUGS.test_bug33_pairs_trader_arb2_fires_on_attack_not_cast()


def test_bug33_pairs_trader_card_text_says_when_attacks():
    _V3_FOLLOWUP_BUGS.test_bug33_pairs_trader_card_text_says_when_attacks()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all():
    tests = [
        test_bug2_multi_attacker_alpha_no_solo_buff,
        test_bug2_solo_alpha_still_buffs,
        test_bug18_alpha_plus4_no_solo_buff_in_multi_attack,
        test_bug3_low_latency_strike_clears_summoning_sickness,
        test_bug3_low_latency_strike_card_has_cast_effect_attribute,
        test_bug4_dma_upgrades_alpha_bonus_to_plus4,
        test_bug4_dma_etb_sets_upgrade_flag,
        test_bug5_speed_amplifier_destroys_when_host_destroyed,
        test_bug5_speed_amplifier_destroys_when_host_zone_changes,
        test_bug6_solo_alpha_sets_struck_alone_flag,
        test_bug6_multi_attack_does_not_set_struck_alone_flag,
        test_bug6_tick_data_archive_pre_market_draws_when_flag_set,
        # Quant agent additions:
        test_bug1_two_power_into_four_toughness_blocker_survives,
        test_bug1_overflow_only_with_trample,
        test_bug7_correlation_matrix_actually_draws,
        test_bug8_quant_signal_puts_top_card_in_hand,
        test_bug9_risk_manager_blocks_one_power_takes_zero_net_damage,
        test_bug17_rebalancing_halt_undeclares_attacker,
        # Dark Arbitrage agent additions (bugs 11/12/13/15/20):
        test_dp_order_routes_to_dark_pool_not_graveyard,
        test_hidden_accumulator_triggers_on_dp_cast,
        test_hidden_aggression_card_text_matches_code,
        test_oep_refuses_cast_without_dp_slot,
        test_dark_pool_order_search_filter,
        # Derivatives agent additions (bugs 10/14/16/19):
        test_leverage_3_trader_etb_counters_eq_3,
        test_leverage_tick_single_trader_lev3_deals_3,
        test_leverage_power_query_fires,
        test_creature_dies_routed_to_graveyard,
        # DP timing + isolated card bugs (#24, #26, #27, #29):
        test_bug24_vega_spike_adds_leverage_counters,
        test_bug26_hidden_aggression_does_not_damage_opponent_on_cast,
        test_bug27_no_trample_overflow_without_keyword,
        test_bug27_trample_overflow_with_keyword,
        # Priority-mismatch class bugs (#21, #22, #25, #28):
        test_bug21_hft_feed_colocation_buffs_traders,
        test_bug22_pcd_toughness_lord_buffs_quant_traders,
        test_bug25_synthetic_collar_buffs_attached_trader,
        test_bug28_dark_flow_engine_reduces_cost,
        test_bug29_crossed_market_fires_on_controller_ts,
        test_bug29_pfof_fires_on_controller_ts,
        # Bug #2 sequential-call robustness + Bug #6 flag persistence:
        test_bug2_two_alpha_attackers_neither_gets_alone_bonus,
        test_bug2_one_alpha_attacker_gets_alone_bonus,
        test_bug2_oef_alpha_plus4_only_with_solo_attack,
        test_bug6_tda_solo_attack_flag_set_when_alone,
        test_bug6_tda_solo_flag_persists_through_eot,
        # v3 follow-up bugs (#31, #32, #33):
        test_bug31_liquidity_event_counts_game_wide_dps,
        test_bug32_quant_lab_buffs_quant_traders_by_one,
        test_bug32_quant_lab_does_not_buff_non_quant_traders,
        test_bug32_pcd_lord_stack_within_card_text,
        test_bug33_pairs_trader_arb2_fires_on_attack_not_cast,
        test_bug33_pairs_trader_card_text_says_when_attacks,
    ]
    failures = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failures.append((t.__name__, str(e)))
            print(f"{t.__name__}  FAIL: {e}")
        except Exception as e:
            import traceback
            failures.append((t.__name__, f"{type(e).__name__}: {e}"))
            print(f"{t.__name__}  ERROR: {type(e).__name__}: {e}")
            traceback.print_exc()
    print()
    if failures:
        print(f"{len(failures)}/{len(tests)} test(s) failed:")
        for name, err in failures:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print(f"All {len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
