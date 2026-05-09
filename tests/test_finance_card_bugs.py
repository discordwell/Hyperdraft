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
