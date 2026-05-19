"""
Dragon Ball Z Spice Pass Tests — v2 EXPANSION (2026-05-18)

Validates the 7 NEW format-defining cards added on top of the existing
Phase A/B spice (which lives in tests/test_dragon_ball_spice.py).

Cards covered (none collide with existing spice names):
- Shenron, Wish Granter (NEW mythic dragon — Dragon Balls assembly payoff)
- Eternal Dragon's Wish (NEW sorcery — assembly tutor / win condition)
- The Saiyan Saga (NEW saga — Saiyan tribal payoff)
- Bardock, Father of Saiyans (NEW Saiyan seer / snowball draw)
- Future Trunks, Tomorrow's Hope (NEW time traveler / spell tutor + recursion)
- Goku, Ultra Instinct Sign (NEW god-tier mythic with ward + counter snowball)
- Kame House, Master's Refuge (NEW Z-Fighter tutor land)

Mirrors test_zelda_spice.py shape — worktree-portable sys.path
(gotcha #18) and canonical helpers (gotcha #16).
"""

import os
import sys
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, get_power, get_toughness,
)
from src.engine.activated import can_pay_activation
from src.cards.custom.dragon_ball import DRAGON_BALL_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern from spice-pass.md: create in hand without card_def,
    then ZONE_CHANGE so the pipeline runs setup_interceptors exactly once."""
    card_def = DRAGON_BALL_CARDS[card_name]
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


def _put_dragon_balls_on_battlefield(game, player, n):
    """Put N actual Dragon Ball artifact cards onto the battlefield."""
    names = [
        "One-Star Dragon Ball", "Two-Star Dragon Ball", "Three-Star Dragon Ball",
        "Four-Star Dragon Ball", "Five-Star Dragon Ball", "Six-Star Dragon Ball",
        "Seven-Star Dragon Ball",
    ]
    out = []
    for nm in names[:n]:
        cd = DRAGON_BALL_CARDS[nm]
        obj = game.create_object(
            name=nm,
            owner_id=player.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=cd.characteristics,
            card_def=cd,
        )
        out.append(obj)
    return out


# ============================================================================
# Shenron, Wish Granter
# ============================================================================

def test_shenron_wish_granter_loads():
    """Mythic Dragon/God with flying+trample static and ETB trigger."""
    print("\n=== Shenron, Wish Granter: load ===")
    cd = DRAGON_BALL_CARDS["Shenron, Wish Granter"]
    assert CardType.CREATURE in cd.characteristics.types
    assert "Dragon" in cd.characteristics.subtypes
    assert "God" in cd.characteristics.subtypes
    assert "Legendary" in (cd.characteristics.supertypes or set())
    game = Game()
    p1 = game.add_player("Alice")
    shen = _put_on_battlefield(game, p1, "Shenron, Wish Granter")
    # 1 keyword grant + 1 ETB trigger.
    assert len(shen.interceptor_ids) >= 2, (
        f"Expected at least 2 interceptors (kw + etb): {len(shen.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(shen.interceptor_ids)}")


def test_shenron_etb_partial_wish_with_no_balls():
    """ETB with 0 Dragon Balls: scry 3 only (no draw)."""
    print("\n=== Shenron: partial wish (0 balls) ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    _put_on_battlefield(game, p1, "Shenron, Wish Granter")
    new_types = _emitted_types(game)[len(before):]
    assert 'SCRY' in new_types, f"SCRY missing: {new_types}"
    # No EXTRA_TURN, no DRAW (0 balls => 0-card draw is skipped).
    assert 'EXTRA_TURN' not in new_types, f"Should NOT take extra turn: {new_types}"
    print(f"  SCRY emitted, no extra turn (correct)")


def test_shenron_etb_partial_wish_with_three_balls():
    """ETB with 3 Dragon Balls: draws 3 + scry 3, no extra turn."""
    print("\n=== Shenron: partial wish (3 balls) ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_dragon_balls_on_battlefield(game, p1, 3)
    before = _emitted_types(game)
    _put_on_battlefield(game, p1, "Shenron, Wish Granter")
    new_types = _emitted_types(game)[len(before):]
    # Find DRAW events Shenron emitted.
    shen_id = None
    for o in game.state.objects.values():
        nm = (o.card_def.name if o.card_def else "")
        if nm == "Shenron, Wish Granter":
            shen_id = o.id
            break
    draws = [e for e in game.state.event_log
             if e.type == EventType.DRAW and e.source == shen_id]
    assert draws, f"DRAW from Shenron missing: {new_types}"
    assert draws[-1].payload.get('amount') == 3, (
        f"Expected draw 3 (one per ball): {draws[-1].payload}"
    )
    assert 'EXTRA_TURN' not in new_types
    print(f"  Drew 3, no extra turn (correct)")


def test_shenron_etb_full_wish_with_seven_balls():
    """ETB with all 7 Dragon Balls: draws 7 + takes an extra turn."""
    print("\n=== Shenron: full wish (7 balls) ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_dragon_balls_on_battlefield(game, p1, 7)
    before = _emitted_types(game)
    _put_on_battlefield(game, p1, "Shenron, Wish Granter")
    new_types = _emitted_types(game)[len(before):]
    assert 'EXTRA_TURN' in new_types, f"EXTRA_TURN missing: {new_types}"
    # Find DRAW events.
    shen_id = None
    for o in game.state.objects.values():
        nm = (o.card_def.name if o.card_def else "")
        if nm == "Shenron, Wish Granter":
            shen_id = o.id
            break
    draws = [e for e in game.state.event_log
             if e.type == EventType.DRAW and e.source == shen_id]
    assert draws and draws[-1].payload.get('amount') == 7
    print(f"  Drew 7 + extra turn (full wish granted)")


# ============================================================================
# Eternal Dragon's Wish
# ============================================================================

def test_eternal_dragons_wish_card_def():
    """Sorcery with wired resolve fn."""
    print("\n=== Eternal Dragon's Wish: card def ===")
    cd = DRAGON_BALL_CARDS["Eternal Dragon's Wish"]
    assert CardType.SORCERY in cd.characteristics.types
    assert cd.resolve is not None
    print(f"  Sorcery resolve: {cd.resolve.__name__}")


def test_eternal_dragons_wish_tutors_without_seven_balls():
    """Without 7 balls: SEARCH_LIBRARY event for a Dragon Ball card."""
    print("\n=== Eternal Dragon's Wish: tutor with 0 balls ===")
    game = Game()
    p1 = game.add_player("Alice")
    cd = DRAGON_BALL_CARDS["Eternal Dragon's Wish"]
    # Stage the spell on the stack so the resolve fn finds the caster.
    spell = game.create_object(
        name="Eternal Dragon's Wish",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    events = cd.resolve([], game.state)
    sls = [e for e in events if e.type == EventType.SEARCH_LIBRARY]
    wins = [e for e in events if e.type == EventType.PLAYER_WINS]
    assert sls, f"SEARCH_LIBRARY missing: {[e.type.name for e in events]}"
    assert sls[-1].payload.get('name_contains') == 'Dragon Ball'
    assert not wins, "Should not win with 0 balls"
    print(f"  Tutored Dragon Ball; no PLAYER_WINS")


def test_eternal_dragons_wish_wins_with_seven_balls():
    """With 7 Dragon Balls: emits 7 SACRIFICE events + PLAYER_WINS."""
    print("\n=== Eternal Dragon's Wish: win with 7 balls ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_dragon_balls_on_battlefield(game, p1, 7)
    cd = DRAGON_BALL_CARDS["Eternal Dragon's Wish"]
    spell = game.create_object(
        name="Eternal Dragon's Wish",
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    events = cd.resolve([], game.state)
    sacs = [e for e in events if e.type == EventType.SACRIFICE]
    wins = [e for e in events if e.type == EventType.PLAYER_WINS]
    assert len(sacs) == 7, f"Expected 7 SACRIFICE events, got {len(sacs)}"
    assert wins, f"PLAYER_WINS missing: {[e.type.name for e in events]}"
    assert wins[-1].payload.get('player') == p1.id
    print(f"  7 sacs + PLAYER_WINS for {p1.id}")


# ============================================================================
# The Saiyan Saga
# ============================================================================

def test_saiyan_saga_loads_as_saga_enchantment():
    """Enchantment with Saga subtype; setup_interceptors registers saga
    framework interceptors."""
    print("\n=== The Saiyan Saga: load ===")
    cd = DRAGON_BALL_CARDS["The Saiyan Saga"]
    assert CardType.ENCHANTMENT in cd.characteristics.types
    assert "Saga" in cd.characteristics.subtypes
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Saiyan Saga")
    # Saga registers: ETB lore, draw-step lore, chapter dispatch — ≥3 iceptors.
    assert len(saga.interceptor_ids) >= 3, (
        f"Saga should register ≥3 interceptors: {len(saga.interceptor_ids)}"
    )
    print(f"  Saga interceptors: {len(saga.interceptor_ids)}")


def test_saiyan_saga_chapter_ii_pumps_each_saiyan():
    """Chapter II handler: emits one COUNTER_ADDED per Saiyan you control."""
    print("\n=== The Saiyan Saga: chapter II ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Saiyan Saga")
    # Two friendly Saiyans on the battlefield.
    for i in range(2):
        game.create_object(
            name=f"Saiyan{i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Saiyan"},
                colors={Color.RED},
                power=2, toughness=2,
            ),
        )
    # Non-Saiyan should NOT receive a counter.
    game.create_object(
        name="HumanFighter",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            colors={Color.WHITE},
            power=2, toughness=2,
        ),
    )
    # Import the chapter handler directly via module attribute lookup.
    import src.cards.custom.dragon_ball as mod
    events = mod._saiyan_saga_ch_ii(saga, game.state)
    counters = [e for e in events if e.type == EventType.COUNTER_ADDED]
    assert len(counters) == 2, f"Expected 2 counter events: {len(counters)}"
    for e in counters:
        assert e.payload.get('counter_type') == '+1/+1'
    print(f"  +1/+1 counter for each of 2 Saiyans (Human skipped)")


def test_saiyan_saga_chapter_iii_drains_opponents():
    """Chapter III handler: each opponent loses life = Saiyans you control;
    you gain that much."""
    print("\n=== The Saiyan Saga: chapter III ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Saiyan Saga")
    # Three Saiyans.
    for i in range(3):
        game.create_object(
            name=f"Saiyan{i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Saiyan"},
                colors={Color.RED},
                power=2, toughness=2,
            ),
        )
    import src.cards.custom.dragon_ball as mod
    events = mod._saiyan_saga_ch_iii(saga, game.state)
    life = [e for e in events if e.type == EventType.LIFE_CHANGE]
    # 1 opponent -3 + 1 self +3 = 2 events.
    assert len(life) == 2, f"Expected 2 LIFE_CHANGE events: {[e.payload for e in life]}"
    drains = [e for e in life if e.payload.get('amount') < 0]
    gains = [e for e in life if e.payload.get('amount') > 0]
    assert drains and drains[0].payload.get('player') == p2.id
    assert drains[0].payload.get('amount') == -3
    assert gains and gains[0].payload.get('player') == p1.id
    assert gains[0].payload.get('amount') == 3
    print(f"  Drained Bob -3, gained Alice +3")


def test_saiyan_saga_chapter_iii_no_saiyans_no_effect():
    """Edge: with 0 Saiyans, chapter III emits nothing."""
    print("\n=== The Saiyan Saga: chapter III (no Saiyans) ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Saiyan Saga")
    import src.cards.custom.dragon_ball as mod
    events = mod._saiyan_saga_ch_iii(saga, game.state)
    assert events == [], f"No Saiyans should yield no events: {events}"
    print(f"  No Saiyans => no drain/gain (correct)")


# ============================================================================
# Bardock, Father of Saiyans
# ============================================================================

def test_bardock_loads_and_etb_emits_scry_plus_tutor():
    """ETB: SCRY 3 + SEARCH_LIBRARY for a Saiyan."""
    print("\n=== Bardock: ETB scry + tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    bardock = _put_on_battlefield(game, p1, "Bardock, Father of Saiyans")
    new_types = _emitted_types(game)[len(before):]
    assert 'SCRY' in new_types, f"SCRY missing: {new_types}"
    assert 'SEARCH_LIBRARY' in new_types, f"SEARCH_LIBRARY missing: {new_types}"
    sls = [e for e in game.state.event_log
           if e.type == EventType.SEARCH_LIBRARY and e.source == bardock.id]
    assert sls and sls[-1].payload.get('subtype') == 'Saiyan'
    print(f"  Scry 3 + Saiyan tutor emitted")


def test_bardock_other_saiyan_etb_triggers_scry_one():
    """When ANOTHER Saiyan enters, Bardock scries 1. Non-Saiyan doesn't trigger."""
    print("\n=== Bardock: other-Saiyan ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    bardock = _put_on_battlefield(game, p1, "Bardock, Father of Saiyans")
    # Drop a Saiyan creature.
    before = _emitted_types(game)
    saiyan = game.create_object(
        name="OtherSaiyan",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Saiyan"},
            colors={Color.RED},
            power=2, toughness=2,
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': saiyan.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    new_types = _emitted_types(game)[len(before):]
    # Find scry events sourced from Bardock during this batch.
    scrys = [e for e in game.state.event_log
             if e.type == EventType.SCRY and e.source == bardock.id]
    # Should have at least one scry from the other-Saiyan trigger.
    assert len(scrys) >= 2, f"Expected ≥2 scrys (ETB + other-Saiyan): {len(scrys)}"
    print(f"  Scrys sourced from Bardock: {len(scrys)}")


def test_bardock_self_etb_does_not_double_trigger_other():
    """Edge: Bardock's own ETB doesn't fire the 'other Saiyan enters' trigger
    (filter excludes src.id == entering.id)."""
    print("\n=== Bardock: self-ETB doesn't double ===")
    game = Game()
    p1 = game.add_player("Alice")
    bardock = _put_on_battlefield(game, p1, "Bardock, Father of Saiyans")
    scrys = [e for e in game.state.event_log
             if e.type == EventType.SCRY and e.source == bardock.id]
    # Self ETB emits SCRY 3 — exactly 1 scry event from self-trigger.
    # If other-trigger also fired on self, we'd have 2.
    assert len(scrys) == 1, f"Self-ETB should fire ONE scry: {[e.payload for e in scrys]}"
    print(f"  Self-ETB scry count == 1 (other-trigger correctly skipped self)")


# ============================================================================
# Future Trunks, Tomorrow's Hope
# ============================================================================

def test_future_trunks_tomorrow_loads_and_etb_tutors_sorcery():
    """ETB emits SEARCH_LIBRARY for a sorcery."""
    print("\n=== Future Trunks Tomorrow: ETB sorcery tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    trunks = _put_on_battlefield(game, p1, "Future Trunks, Tomorrow's Hope")
    sls = [e for e in game.state.event_log
           if e.type == EventType.SEARCH_LIBRARY and e.source == trunks.id]
    assert sls, f"SEARCH_LIBRARY not emitted on ETB"
    assert sls[-1].payload.get('card_type') == 'sorcery'
    assert sls[-1].payload.get('max_mana_value') == 4
    print(f"  Sorcery tutor (MV ≤ 4) emitted")


def test_future_trunks_tomorrow_attack_recurs_low_mv_creature():
    """Attack trigger returns smallest-MV creature from graveyard to hand."""
    print("\n=== Future Trunks Tomorrow: attack recursion ===")
    game = Game()
    p1 = game.add_player("Alice")
    trunks = _put_on_battlefield(game, p1, "Future Trunks, Tomorrow's Hope")

    # Put a small creature in graveyard.
    small_creature = game.create_object(
        name="SmallSaiyan",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Saiyan"},
            colors={Color.RED},
            mana_cost="{1}{R}",
            power=2, toughness=2,
        ),
    )
    # And a too-big one.
    big_creature = game.create_object(
        name="BigBeast",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.RED},
            mana_cost="{4}{R}{R}",
            power=6, toughness=6,
        ),
    )

    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': trunks.id},
        source=trunks.id,
    ))
    rfgs = [e for e in game.state.event_log
            if e.type == EventType.RETURN_FROM_GRAVEYARD and e.source == trunks.id]
    assert rfgs, f"RETURN_FROM_GRAVEYARD not fired: {_emitted_types(game)[len(before):]}"
    # Should pick the small (MV≤3) one, not the big one.
    assert rfgs[-1].payload.get('object_id') == small_creature.id
    assert rfgs[-1].payload.get('destination') == 'hand'
    print(f"  Returned SmallSaiyan to hand (Big skipped)")


def test_future_trunks_tomorrow_attack_no_eligible_creature_no_op():
    """Edge: no creature ≤MV3 in graveyard → no events on attack."""
    print("\n=== Future Trunks Tomorrow: empty GY edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    trunks = _put_on_battlefield(game, p1, "Future Trunks, Tomorrow's Hope")
    # Only a too-big creature in graveyard.
    game.create_object(
        name="HugeBeast",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            colors={Color.RED},
            mana_cost="{5}{R}{R}",
            power=8, toughness=8,
        ),
    )
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': trunks.id},
        source=trunks.id,
    ))
    rfgs = [e for e in game.state.event_log
            if e.type == EventType.RETURN_FROM_GRAVEYARD and e.source == trunks.id]
    assert not rfgs, f"Should not recur when no candidate ≤MV3: {rfgs}"
    print(f"  No recursion when only big creatures in GY (correct)")


# ============================================================================
# Goku, Ultra Instinct Sign
# ============================================================================

def test_goku_ultra_instinct_sign_loads_with_ward_and_keywords():
    """Self flying/vigilance grant + ward + target trigger + end-step trigger."""
    print("\n=== Goku UI Sign: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    goku = _put_on_battlefield(game, p1, "Goku, Ultra Instinct Sign")
    # Expect at least 4 interceptors: 1 kw_grant + 1 ward + 1 target trigger + 1 end-step.
    assert len(goku.interceptor_ids) >= 4, (
        f"Expected ≥4 interceptors: {len(goku.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(goku.interceptor_ids)}")


def test_goku_ultra_instinct_sign_target_trigger_adds_counter_and_untaps():
    """When Goku is targeted, +1/+1 counter + untap fire."""
    print("\n=== Goku UI Sign: targeting trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    goku = _put_on_battlefield(game, p1, "Goku, Ultra Instinct Sign")
    # Tap Goku so we can verify untap fires.
    goku.state.tapped = True
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.TARGET_CHOSEN,
        payload={'target_id': goku.id, 'source_id': 'fake_spell'},
        source='fake_spell',
    ))
    new_types = _emitted_types(game)[len(before):]
    assert 'COUNTER_ADDED' in new_types, f"COUNTER_ADDED missing: {new_types}"
    assert 'UNTAP' in new_types, f"UNTAP missing: {new_types}"
    cas = [e for e in game.state.event_log
           if e.type == EventType.COUNTER_ADDED
           and e.payload.get('object_id') == goku.id]
    assert cas and cas[-1].payload.get('counter_type') == '+1/+1'
    print(f"  +1/+1 counter + UNTAP both fired on TARGET_CHOSEN")


def test_goku_ultra_instinct_sign_extra_turn_gated_by_counters():
    """End-step extra turn fires only with 4+ counters; one-shot per game."""
    print("\n=== Goku UI Sign: end-step extra-turn gate ===")
    game = Game()
    p1 = game.add_player("Alice")
    goku = _put_on_battlefield(game, p1, "Goku, Ultra Instinct Sign")
    game.state.active_player = p1.id

    # With <4 counters: no extra turn.
    goku.state.counters['+1/+1'] = 2
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new_types = _emitted_types(game)[len(before):]
    assert 'EXTRA_TURN' not in new_types, f"Should not extra-turn with 2 counters: {new_types}"

    # With 4 counters: extra turn fires.
    goku.state.counters['+1/+1'] = 4
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new_types = _emitted_types(game)[len(before):]
    assert 'EXTRA_TURN' in new_types, f"EXTRA_TURN missing with 4 counters: {new_types}"

    # One-shot: re-firing end-step doesn't extra-turn again.
    before = _emitted_types(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new_types = _emitted_types(game)[len(before):]
    assert 'EXTRA_TURN' not in new_types, (
        f"One-shot violated — extra turn fired twice: {new_types}"
    )
    print(f"  Gated correctly: 2 counters skipped, 4 counters fired ONCE")


# ============================================================================
# Kame House, Master's Refuge
# ============================================================================

def test_kame_house_refuge_loads_as_legendary_land():
    """Land + Legendary; 3 activated abilities ({T}:W, {T}:U, {2}{T}: tutor)."""
    print("\n=== Kame House Refuge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kh = _put_on_battlefield(game, p1, "Kame House, Master's Refuge")
    chars = kh.characteristics
    assert CardType.LAND in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    abilities = getattr(kh.state, 'activated_abilities', [])
    assert len(abilities) >= 3, (
        f"Expected ≥3 activated abilities (W, U, tutor): {len(abilities)}"
    )
    print(f"  Land+Legendary, abilities={len(abilities)}")


def test_kame_house_refuge_tutor_gated_by_z_fighter():
    """Tutor ability legal only when a Z-Fighter is on the battlefield."""
    print("\n=== Kame House Refuge: gate ===")
    game = Game()
    p1 = game.add_player("Alice")
    kh = _put_on_battlefield(game, p1, "Kame House, Master's Refuge")

    abilities = kh.state.activated_abilities or []
    tutor = next(
        (a for a in abilities if a.cost_text and '{2}' in a.cost_text and '{T}' in a.cost_text),
        None,
    )
    assert tutor is not None, f"Tutor not found: {[a.cost_text for a in abilities]}"

    # No Z-Fighters: not legal.
    legal_no = can_pay_activation(tutor, kh, game.state, p1.id, mana_system=None)
    assert not legal_no, "Tutor should NOT be legal without a Z-Fighter"

    # Add a Z-Fighter: legal.
    game.create_object(
        name="SomeZFighter",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Z-Fighter"},
            colors={Color.WHITE},
            power=1, toughness=1,
        ),
    )
    legal_yes = can_pay_activation(tutor, kh, game.state, p1.id, mana_system=None)
    assert legal_yes, "Tutor should be legal with a Z-Fighter present"
    print(f"  Gate: no Z-Fighter blocked, with Z-Fighter unlocked")


# ============================================================================
# SLICE 4 — Thin-bust: 17 vanilla cards lifted to depth-3 axes
# Each card now emits SCRY or REVEAL or DISCARD/LIFE_CHANGE to opponent,
# reads state.zones, and counts allies by subtype/type.
# ============================================================================


def _events_emitted_by(game, source_id, event_type):
    return [e for e in game.state.event_log
            if e.type == event_type and e.source == source_id]


def _assert_etb_scry(game, p1, card_name, expected_amount=1):
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


def test_yamcha_attack_emits_scry_and_life_drain():
    """Yamcha (W Z-Fighter) — on attack, scry 1 + each opp loses 1 life."""
    print("\n=== Yamcha, Z-Fighter: attack trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    yam = _put_on_battlefield(game, p1, "Yamcha, Z-Fighter")
    # Yamcha registers an attack trigger.
    assert len(yam.interceptor_ids) >= 1
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': yam.id, 'defender': p2.id},
    ))
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events
              if e.type == EventType.SCRY and e.source == yam.id]
    drains = [e for e in new_events
              if e.type == EventType.LIFE_CHANGE
              and e.source == yam.id
              and e.payload.get('amount') == -1]
    assert scries, f"SCRY missing: {[e.type.name for e in new_events]}"
    assert drains, f"LIFE_CHANGE drain missing: {[e.type.name for e in new_events]}"
    print(f"  Yamcha attack: SCRY + {len(drains)} life-drain emitted")


def test_chiaotzu_etb_scry_and_surveil_with_threat():
    """Chiaotzu (W Z-Fighter) — ETB scry 1 + surveil 1 if opp has threats."""
    print("\n=== Chiaotzu: psychic ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Put a threat on opp battlefield so the surveil branch fires.
    threat_cd = DRAGON_BALL_CARDS["Saiyan Warrior"]
    game.create_object(
        name="Saiyan Warrior",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=threat_cd.characteristics,
        card_def=threat_cd,
    )
    obj = _assert_etb_scry(game, p1, "Chiaotzu, Psychic Fighter", expected_amount=1)
    surveils = _events_emitted_by(game, obj.id, EventType.SURVEIL)
    assert surveils, f"SURVEIL missing for Chiaotzu"
    print(f"  Chiaotzu: SCRY + {len(surveils)} surveil(s)")


def test_kami_etb_scry_and_life_gain():
    """Kami (W Namekian God) — ETB scry 2 + gain life per creature you control."""
    print("\n=== Kami, Guardian of Earth: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Kami, Guardian of Earth", expected_amount=2)
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE
             and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "LIFE_CHANGE (gain) missing for Kami"
    print(f"  Kami: SCRY 2 + life gain {gains[-1].payload}")


def test_mr_popo_etb_scry_and_life_gain():
    """Mr. Popo (W Genie) — ETB scry 1 + gain 1 life per artifact you control."""
    print("\n=== Mr. Popo: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Mr. Popo, Eternal Servant")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE
             and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains, "LIFE_CHANGE missing for Mr. Popo"
    print(f"  Mr. Popo: SCRY + life gain {gains[-1].payload}")


def test_earthling_fighter_attack_scry_and_drain():
    """Earthling Fighter (W Human Warrior) — attack scry 1 + opp -1 life."""
    print("\n=== Earthling Fighter: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ef = _put_on_battlefield(game, p1, "Earthling Fighter")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': ef.id, 'defender': p2.id},
    ))
    new_events = game.state.event_log[before:]
    scries = [e for e in new_events if e.type == EventType.SCRY and e.source == ef.id]
    drains = [e for e in new_events
              if e.type == EventType.LIFE_CHANGE and e.source == ef.id
              and e.payload.get('amount') == -1]
    assert scries and drains
    print(f"  Earthling Fighter: SCRY + drain")


def test_capsule_corp_soldier_etb_scry_and_life_gain():
    """Capsule Corp Soldier — ETB scry 1 + gain life per Soldier."""
    print("\n=== Capsule Corp Soldier: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Capsule Corp Soldier")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) > 0]
    assert gains
    print(f"  Capsule Corp Soldier: SCRY + life gain")


def test_martial_artist_attack_scry_and_drain():
    """Martial Artist (W Monk) — attack scry 1 + opp -1 life."""
    print("\n=== Martial Artist: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ma = _put_on_battlefield(game, p1, "Martial Artist")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': ma.id, 'defender': p2.id},
    ))
    new_events = game.state.event_log[before:]
    assert any(e.type == EventType.SCRY and e.source == ma.id for e in new_events)
    assert any(e.type == EventType.LIFE_CHANGE and e.source == ma.id
               and e.payload.get('amount') == -1 for e in new_events)
    print(f"  Martial Artist: SCRY + drain")


def test_guardian_angel_etb_scry_and_life_gain():
    """Guardian Angel — ETB scry 1 + gain ≥2 life."""
    print("\n=== Guardian Angel: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    obj = _assert_etb_scry(game, p1, "Guardian Angel")
    gains = [e for e in game.state.event_log
             if e.type == EventType.LIFE_CHANGE and e.source == obj.id
             and e.payload.get('amount', 0) >= 2]
    assert gains
    print(f"  Guardian Angel: SCRY + life gain {gains[-1].payload}")


def test_android_prototype_etb_scry_and_surveil():
    """Android Prototype (U Android) — ETB scry 1 + surveil 1 if opp has creatures."""
    print("\n=== Android Prototype: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    threat_cd = DRAGON_BALL_CARDS["Saiyan Warrior"]
    game.create_object(
        name="Saiyan Warrior",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=threat_cd.characteristics,
        card_def=threat_cd,
    )
    obj = _assert_etb_scry(game, p1, "Android Prototype")
    surveils = _events_emitted_by(game, obj.id, EventType.SURVEIL)
    assert surveils
    print(f"  Android Prototype: SCRY + {len(surveils)} surveil(s)")


def test_battle_android_etb_scry_and_damage():
    """Battle Android — ETB scry 1 + deal 1 damage to each opponent."""
    print("\n=== Battle Android: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Battle Android")
    dmgs = _events_emitted_by(game, obj.id, EventType.DAMAGE)
    assert dmgs, "DAMAGE missing for Battle Android"
    assert dmgs[-1].payload.get('amount') == 1
    print(f"  Battle Android: SCRY + {len(dmgs)} damage(s)")


def test_burter_attack_scry_and_drain():
    """Burter (B Ginyu Force) — attack scry 1 + each opp -1 life."""
    print("\n=== Burter: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bur = _put_on_battlefield(game, p1, "Burter")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bur.id, 'defender': p2.id},
    ))
    new_events = game.state.event_log[before:]
    assert any(e.type == EventType.SCRY and e.source == bur.id for e in new_events)
    drains = [e for e in new_events
              if e.type == EventType.LIFE_CHANGE and e.source == bur.id
              and e.payload.get('amount') == -1]
    assert drains
    print(f"  Burter: SCRY + drain")


def test_guldo_etb_scry_two_and_reveal_hand():
    """Guldo (B Ginyu Force) — ETB scry 2 + reveal each opp's hand."""
    print("\n=== Guldo: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Guldo", expected_amount=2)
    looks = _events_emitted_by(game, obj.id, EventType.REVEAL_HAND)
    assert looks
    print(f"  Guldo: SCRY 2 + {len(looks)} reveal_hand(s)")


def test_appule_etb_scry_and_drain():
    """Appule (B Alien) — ETB scry 1 + each opp -1 life."""
    print("\n=== Appule: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Appule")
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount') == -1]
    assert drains
    print(f"  Appule: SCRY + drain")


def test_babidi_etb_discard_and_drain():
    """Babidi (B Wizard) — ETB each opp discards 1 + each opp -1 life."""
    print("\n=== Babidi: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Babidi, Dark Wizard")
    discards = _events_emitted_by(game, obj.id, EventType.DISCARD)
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount') == -1]
    assert discards, "DISCARD missing for Babidi"
    assert drains, "LIFE_CHANGE drain missing for Babidi"
    print(f"  Babidi: {len(discards)} discard(s) + {len(drains)} drain(s)")


def test_nappa_etb_scry_and_damage():
    """Nappa (R Saiyan, Legendary, menace) — ETB scry 1 + damage to each opp."""
    print("\n=== Nappa: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _assert_etb_scry(game, p1, "Nappa, Saiyan Elite")
    dmgs = _events_emitted_by(game, obj.id, EventType.DAMAGE)
    assert dmgs
    print(f"  Nappa: SCRY + {len(dmgs)} damage(s)")


def test_raditz_etb_scry_reveal_hand_and_drain():
    """Raditz (R Saiyan) — ETB scry 1 + each opp reveals hand + -1 life."""
    print("\n=== Raditz: ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Raditz, Saiyan Warrior")
    scries = _events_emitted_by(game, obj.id, EventType.SCRY)
    reveals = _events_emitted_by(game, obj.id, EventType.REVEAL_HAND)
    drains = [e for e in game.state.event_log
              if e.type == EventType.LIFE_CHANGE and e.source == obj.id
              and e.payload.get('amount') == -1]
    assert scries, "SCRY missing for Raditz"
    assert reveals, "REVEAL_HAND missing for Raditz"
    assert drains, "LIFE_CHANGE drain missing for Raditz"
    print(f"  Raditz: SCRY + {len(reveals)} reveal_hand(s) + {len(drains)} drain(s)")


def test_saiyan_warrior_attack_scry_and_damage():
    """Saiyan Warrior (R) — attack scry 1 + damage to each opp."""
    print("\n=== Saiyan Warrior: attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sw = _put_on_battlefield(game, p1, "Saiyan Warrior")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sw.id, 'defender': p2.id},
    ))
    new_events = game.state.event_log[before:]
    assert any(e.type == EventType.SCRY and e.source == sw.id for e in new_events)
    dmgs = [e for e in new_events
            if e.type == EventType.DAMAGE and e.source == sw.id]
    assert dmgs
    print(f"  Saiyan Warrior: SCRY + {len(dmgs)} damage(s)")


if __name__ == "__main__":
    # Shenron
    test_shenron_wish_granter_loads()
    test_shenron_etb_partial_wish_with_no_balls()
    test_shenron_etb_partial_wish_with_three_balls()
    test_shenron_etb_full_wish_with_seven_balls()
    # Eternal Dragon's Wish
    test_eternal_dragons_wish_card_def()
    test_eternal_dragons_wish_tutors_without_seven_balls()
    test_eternal_dragons_wish_wins_with_seven_balls()
    # The Saiyan Saga
    test_saiyan_saga_loads_as_saga_enchantment()
    test_saiyan_saga_chapter_ii_pumps_each_saiyan()
    test_saiyan_saga_chapter_iii_drains_opponents()
    test_saiyan_saga_chapter_iii_no_saiyans_no_effect()
    # Bardock
    test_bardock_loads_and_etb_emits_scry_plus_tutor()
    test_bardock_other_saiyan_etb_triggers_scry_one()
    test_bardock_self_etb_does_not_double_trigger_other()
    # Future Trunks Tomorrow
    test_future_trunks_tomorrow_loads_and_etb_tutors_sorcery()
    test_future_trunks_tomorrow_attack_recurs_low_mv_creature()
    test_future_trunks_tomorrow_attack_no_eligible_creature_no_op()
    # Goku UI Sign
    test_goku_ultra_instinct_sign_loads_with_ward_and_keywords()
    test_goku_ultra_instinct_sign_target_trigger_adds_counter_and_untaps()
    test_goku_ultra_instinct_sign_extra_turn_gated_by_counters()
    # Kame House
    test_kame_house_refuge_loads_as_legendary_land()
    test_kame_house_refuge_tutor_gated_by_z_fighter()
    # Slice 4 — thin-bust (17 vanilla cards lifted to depth-3)
    test_yamcha_attack_emits_scry_and_life_drain()
    test_chiaotzu_etb_scry_and_surveil_with_threat()
    test_kami_etb_scry_and_life_gain()
    test_mr_popo_etb_scry_and_life_gain()
    test_earthling_fighter_attack_scry_and_drain()
    test_capsule_corp_soldier_etb_scry_and_life_gain()
    test_martial_artist_attack_scry_and_drain()
    test_guardian_angel_etb_scry_and_life_gain()
    test_android_prototype_etb_scry_and_surveil()
    test_battle_android_etb_scry_and_damage()
    test_burter_attack_scry_and_drain()
    test_guldo_etb_scry_two_and_reveal_hand()
    test_appule_etb_scry_and_drain()
    test_babidi_etb_discard_and_drain()
    test_nappa_etb_scry_and_damage()
    test_raditz_etb_scry_reveal_hand_and_drain()
    test_saiyan_warrior_attack_scry_and_damage()
    print("\n" + "=" * 60)
    print("ALL DBZ SPICE v2 EXPANSION TESTS PASSED!")
    print("=" * 60)
