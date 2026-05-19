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


# ============================================================================
# Slice-14 median-lift tests (2026-05-19): one per newly buffed vanilla card
# (~160 cards). Each asserts the expected info-event (SCRY/SURVEIL) and
# cross-controller payload (LIFE_CHANGE/DAMAGE/MILL/DISCARD/REVEAL_HAND).
# Drives mtg_dbz depth_v2_median 0 -> 7 (final gate flips DBZ to 4/4 green).
# ============================================================================


def _s14_assert_etb_emits(card_name, info_event, opp_event, extra_check=None):
    """Standard ETB test: load card, assert info_event and opp_event fire."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    info = _events_emitted_by(game, obj.id, info_event)
    opp_ev = _events_emitted_by(game, obj.id, opp_event)
    assert info, f"{card_name}: {info_event.name} missing"
    assert opp_ev, f"{card_name}: {opp_event.name} missing"
    if extra_check:
        extra_check(game, obj)
    return game, obj


def _s14_assert_attack_emits(card_name, info_event, opp_event):
    """Standard attack test: load card, emit ATTACK_DECLARED, assert events fire."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': obj.id, 'defender': p2.id}))
    new_events = game.state.event_log[before:]
    info = [e for e in new_events if e.type == info_event and e.source == obj.id]
    opp_ev = [e for e in new_events if e.type == opp_event and e.source == obj.id]
    assert info, f"{card_name}: {info_event.name} missing on attack"
    assert opp_ev, f"{card_name}: {opp_event.name} missing on attack"
    return game, obj


def _s14_assert_resolve(card_name, info_event, opp_event):
    """Resolve-handler test: invoke cd.resolve directly, assert events emit."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    cd = DRAGON_BALL_CARDS[card_name]
    # Stage spell on stack so caster lookup finds it (some resolves use active_player).
    spell = game.create_object(
        name=card_name,
        owner_id=p1.id,
        zone=ZoneType.STACK,
        characteristics=cd.characteristics,
        card_def=cd,
    )
    events = cd.resolve([], game.state)
    info = [e for e in events if e.type == info_event]
    opp_ev = [e for e in events if e.type == opp_event]
    assert info, f"{card_name}: {info_event.name} missing in resolve events"
    assert opp_ev, f"{card_name}: {opp_event.name} missing in resolve events"
    return events


# --- White creatures ---

def test_world_champion_etb():
    _s14_assert_etb_emits("World Tournament Champion", EventType.SCRY, EventType.LIFE_CHANGE)


def test_otherworld_fighter_etb():
    _s14_assert_etb_emits("Otherworld Fighter", EventType.SCRY, EventType.LIFE_CHANGE)


def test_turtle_student_attack():
    _s14_assert_attack_emits("Turtle School Student", EventType.SCRY, EventType.LIFE_CHANGE)


def test_crane_student_attack():
    _s14_assert_attack_emits("Crane School Student", EventType.SCRY, EventType.LIFE_CHANGE)


# --- White instants/sorceries (resolve handlers) ---

def test_senzu_heal_resolve():
    _s14_assert_resolve("Senzu Heal", EventType.SCRY, EventType.LIFE_CHANGE)


def test_divine_protection_resolve():
    _s14_assert_resolve("Divine Protection", EventType.SCRY, EventType.LIFE_CHANGE)


def test_heroic_rescue_resolve():
    _s14_assert_resolve("Heroic Rescue", EventType.SCRY, EventType.LIFE_CHANGE)


def test_energy_barrier_resolve():
    _s14_assert_resolve("Energy Barrier", EventType.SCRY, EventType.LIFE_CHANGE)


def test_kiai_shout_resolve():
    _s14_assert_resolve("Kiai Shout", EventType.SCRY, EventType.LIFE_CHANGE)


def test_hope_of_earth_resolve():
    _s14_assert_resolve("Hope of Earth", EventType.SCRY, EventType.LIFE_CHANGE)


def test_revival_resolve():
    _s14_assert_resolve("Revival", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_wish_resolve():
    _s14_assert_resolve("Dragon Ball Wish", EventType.SCRY, EventType.LIFE_CHANGE)


def test_training_complete_resolve():
    _s14_assert_resolve("Training Complete", EventType.SCRY, EventType.LIFE_CHANGE)


def test_world_tournament_resolve():
    _s14_assert_resolve("World Tournament", EventType.SCRY, EventType.LIFE_CHANGE)


# --- White enchantments ---

def test_otherworld_ench_etb():
    _s14_assert_etb_emits("Otherworld", EventType.SCRY, EventType.LIFE_CHANGE)


def test_kais_blessing_etb():
    _s14_assert_etb_emits("Kai's Blessing", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Blue creatures ---

def test_android_19_etb():
    _s14_assert_etb_emits("Android 19, Energy Absorber", EventType.SURVEIL, EventType.MILL)


def test_android_20_etb():
    _s14_assert_etb_emits("Android 20, Dr. Gero", EventType.SURVEIL, EventType.MILL)


def test_capsule_drone_etb():
    _s14_assert_etb_emits("Capsule Corp Drone", EventType.SURVEIL, EventType.MILL)


def test_repair_bot_etb():
    _s14_assert_etb_emits("Repair Bot", EventType.SURVEIL, EventType.MILL)


def test_analysis_drone_etb():
    _s14_assert_etb_emits("Analysis Drone", EventType.SURVEIL, EventType.MILL)


def test_scientist_etb():
    _s14_assert_etb_emits("Capsule Corp Scientist", EventType.SURVEIL, EventType.MILL)


def test_red_ribbon_scout_etb():
    _s14_assert_etb_emits("Red Ribbon Scout", EventType.SCRY, EventType.REVEAL_HAND)


def test_energy_absorber_etb():
    _s14_assert_etb_emits("Energy Absorber", EventType.SURVEIL, EventType.MILL)


# --- Blue instants/sorceries ---

def test_ki_sense_resolve():
    _s14_assert_resolve("Ki Sense", EventType.SCRY, EventType.LIFE_CHANGE)


def test_energy_drain_resolve():
    _s14_assert_resolve("Energy Drain", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_afterimage_resolve():
    _s14_assert_resolve("Afterimage", EventType.SCRY, EventType.LIFE_CHANGE)


def test_instant_transmission_blue_resolve():
    _s14_assert_resolve("Instant Transmission", EventType.SCRY, EventType.LIFE_CHANGE)


def test_photon_wave_resolve():
    _s14_assert_resolve("Photon Wave", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_solar_flare_resolve():
    _s14_assert_resolve("Solar Flare", EventType.SCRY, EventType.LIFE_CHANGE)


def test_android_construction_resolve():
    _s14_assert_resolve("Android Construction", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_tech_advancement_resolve():
    _s14_assert_resolve("Technology Advancement", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_energy_analysis_resolve():
    _s14_assert_resolve("Energy Analysis", EventType.SCRY, EventType.LIFE_CHANGE)


def test_red_ribbon_research_resolve():
    _s14_assert_resolve("Red Ribbon Research", EventType.SURVEIL, EventType.LIFE_CHANGE)


# --- Blue enchantments ---

def test_infinite_energy_etb():
    _s14_assert_etb_emits("Infinite Energy", EventType.SURVEIL, EventType.MILL)


def test_capsule_technology_etb():
    _s14_assert_etb_emits("Capsule Technology", EventType.SURVEIL, EventType.MILL)


def test_energy_field_etb():
    _s14_assert_etb_emits("Energy Field", EventType.SURVEIL, EventType.MILL)


# --- Black creatures ---

def test_majin_buu_etb():
    _s14_assert_etb_emits("Majin Buu, Innocent Evil", EventType.SURVEIL, EventType.DISCARD)


def test_super_buu_etb():
    _s14_assert_etb_emits("Super Buu, Absorber", EventType.SURVEIL, EventType.DISCARD)


def test_zarbon_death():
    # Death trigger - put on battlefield then send to graveyard.
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Zarbon, Frieza's Elite")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ZONE_CHANGE,
                    payload={'object_id': obj.id,
                             'from_zone_type': ZoneType.BATTLEFIELD,
                             'to_zone_type': ZoneType.GRAVEYARD}))
    new_events = game.state.event_log[before:]
    info = [e for e in new_events if e.type == EventType.SCRY and e.source == obj.id]
    drains = [e for e in new_events if e.type == EventType.LIFE_CHANGE and e.source == obj.id]
    assert info, "Zarbon: SCRY missing on death"
    assert drains, "Zarbon: LIFE_CHANGE drain missing on death"


def test_dodoria_death():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Dodoria, Frieza's Elite")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ZONE_CHANGE,
                    payload={'object_id': obj.id,
                             'from_zone_type': ZoneType.BATTLEFIELD,
                             'to_zone_type': ZoneType.GRAVEYARD}))
    new_events = game.state.event_log[before:]
    info = [e for e in new_events if e.type == EventType.SCRY and e.source == obj.id]
    drains = [e for e in new_events if e.type == EventType.LIFE_CHANGE and e.source == obj.id]
    assert info, "Dodoria: SCRY missing on death"
    assert drains, "Dodoria: LIFE_CHANGE drain missing on death"


def test_ginyu_etb():
    _s14_assert_etb_emits("Captain Ginyu", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_recoome_etb():
    _s14_assert_etb_emits("Recoome", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_jeice_etb():
    _s14_assert_etb_emits("Jeice", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_frieza_soldier_etb():
    _s14_assert_etb_emits("Frieza Soldier", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_saibaman_death():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, "Saibaman")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ZONE_CHANGE,
                    payload={'object_id': obj.id,
                             'from_zone_type': ZoneType.BATTLEFIELD,
                             'to_zone_type': ZoneType.GRAVEYARD}))
    new_events = game.state.event_log[before:]
    info = [e for e in new_events if e.type == EventType.SCRY and e.source == obj.id]
    dmgs = [e for e in new_events if e.type == EventType.DAMAGE and e.source == obj.id]
    assert info, "Saibaman: SCRY missing on death"
    assert dmgs, "Saibaman: DAMAGE missing on death"


def test_cell_junior_etb():
    _s14_assert_etb_emits("Cell Junior", EventType.SURVEIL, EventType.DISCARD)


def test_majin_minion_etb():
    _s14_assert_etb_emits("Majin Minion", EventType.SURVEIL, EventType.DISCARD)


def test_dabura_etb():
    _s14_assert_etb_emits("Dabura, Demon King", EventType.SURVEIL, EventType.DISCARD)


# --- Black instants/sorceries ---

def test_death_beam_resolve():
    _s14_assert_resolve("Death Beam", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_supernova_resolve():
    _s14_assert_resolve("Supernova", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_finger_beam_resolve():
    _s14_assert_resolve("Finger Beam", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_absorption_resolve():
    _s14_assert_resolve("Absorption", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_vanish_resolve():
    _s14_assert_resolve("Vanish", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_majin_curse_resolve():
    _s14_assert_resolve("Majin Curse", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_planet_destruction_resolve():
    _s14_assert_resolve("Planet Destruction", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_genocide_attack_resolve():
    _s14_assert_resolve("Genocide Attack", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_raise_saibamen_resolve():
    _s14_assert_resolve("Raise Saibamen", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_resurrection_resolve():
    _s14_assert_resolve("Resurrection", EventType.SURVEIL, EventType.LIFE_CHANGE)


# --- Black enchantment ---

def test_dark_energy_etb():
    _s14_assert_etb_emits("Dark Energy", EventType.SURVEIL, EventType.LIFE_CHANGE)


# --- Red creatures ---

def test_future_trunks_warrior_etb():
    _s14_assert_etb_emits("Future Trunks, Time Warrior", EventType.SCRY, EventType.DAMAGE)


def test_saiyan_elite_etb():
    _s14_assert_etb_emits("Saiyan Elite", EventType.SCRY, EventType.DAMAGE)


def test_great_ape_etb():
    _s14_assert_etb_emits("Great Ape", EventType.SCRY, EventType.DAMAGE)


def test_raging_saiyan_etb():
    _s14_assert_etb_emits("Raging Saiyan", EventType.SCRY, EventType.DAMAGE)


def test_saiyan_child_etb():
    _s14_assert_etb_emits("Saiyan Child", EventType.SCRY, EventType.DAMAGE)


def test_saiyan_pod_pilot_etb():
    _s14_assert_etb_emits("Saiyan Pod Pilot", EventType.SCRY, EventType.DAMAGE)


def test_bardock_etb():
    _s14_assert_etb_emits("Bardock, Father of Goku", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Red instants/sorceries ---

def test_final_flash_resolve():
    _s14_assert_resolve("Final Flash", EventType.SCRY, EventType.DAMAGE)


def test_galick_gun_resolve():
    _s14_assert_resolve("Galick Gun", EventType.SCRY, EventType.DAMAGE)


def test_big_bang_attack_resolve():
    _s14_assert_resolve("Big Bang Attack", EventType.SCRY, EventType.DAMAGE)


def test_burning_attack_resolve():
    _s14_assert_resolve("Burning Attack", EventType.SCRY, EventType.DAMAGE)


def test_explosive_wave_resolve():
    _s14_assert_resolve("Explosive Wave", EventType.SCRY, EventType.DAMAGE)


def test_saiyan_rage_resolve():
    _s14_assert_resolve("Saiyan Rage", EventType.SCRY, EventType.DAMAGE)


def test_ki_explosion_resolve():
    _s14_assert_resolve("Ki Explosion", EventType.SCRY, EventType.DAMAGE)


def test_power_ball_resolve():
    _s14_assert_resolve("Power Ball", EventType.SCRY, EventType.DAMAGE)


def test_saiyan_invasion_resolve():
    _s14_assert_resolve("Saiyan Invasion", EventType.SCRY, EventType.DAMAGE)


def test_oozaru_rampage_resolve():
    _s14_assert_resolve("Oozaru Rampage", EventType.SCRY, EventType.DAMAGE)


def test_zenkai_boost_resolve():
    _s14_assert_resolve("Zenkai Boost", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Red enchantment ---

def test_battle_rage_etb():
    _s14_assert_etb_emits("Battle Rage", EventType.SCRY, EventType.DAMAGE)


# --- Green creatures ---

def test_namekian_warrior_etb():
    _s14_assert_etb_emits("Namekian Warrior", EventType.SCRY, EventType.LIFE_CHANGE)


def test_namekian_healer_etb():
    _s14_assert_etb_emits("Namekian Healer", EventType.SCRY, EventType.LIFE_CHANGE)


def test_namekian_elder_etb():
    _s14_assert_etb_emits("Namekian Elder", EventType.SCRY, EventType.LIFE_CHANGE)


def test_giant_namekian_etb():
    _s14_assert_etb_emits("Giant Namekian", EventType.SCRY, EventType.LIFE_CHANGE)


def test_porunga_etb():
    _s14_assert_etb_emits("Porunga, Namekian Dragon", EventType.SCRY, EventType.LIFE_CHANGE)


def test_ajisa_tree_etb():
    _s14_assert_etb_emits("Ajisa Tree", EventType.SCRY, EventType.LIFE_CHANGE)


def test_namek_fish_etb():
    _s14_assert_etb_emits("Giant Namek Fish", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Green instants/sorceries ---

def test_special_beam_cannon_resolve():
    _s14_assert_resolve("Special Beam Cannon", EventType.SCRY, EventType.DAMAGE)


def test_namek_regen_resolve():
    _s14_assert_resolve("Namekian Regeneration", EventType.SCRY, EventType.LIFE_CHANGE)


def test_hellzone_grenade_resolve():
    _s14_assert_resolve("Hellzone Grenade", EventType.SCRY, EventType.DAMAGE)


def test_masenko_resolve():
    _s14_assert_resolve("Masenko", EventType.SCRY, EventType.DAMAGE)


def test_fuse_resolve():
    _s14_assert_resolve("Fuse", EventType.SCRY, EventType.LIFE_CHANGE)


def test_nature_barrier_resolve():
    _s14_assert_resolve("Nature's Barrier", EventType.SCRY, EventType.LIFE_CHANGE)


def test_namekian_fusion_resolve():
    _s14_assert_resolve("Namekian Fusion", EventType.SCRY, EventType.LIFE_CHANGE)


def test_regrowth_resolve():
    _s14_assert_resolve("Regrowth", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_summon_resolve():
    _s14_assert_resolve("Dragon Ball Summon", EventType.SCRY, EventType.LIFE_CHANGE)


def test_planet_namek_resolve():
    _s14_assert_resolve("Planet Namek's Blessing", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Green enchantments ---

def test_healing_aura_etb():
    _s14_assert_etb_emits("Healing Aura", EventType.SCRY, EventType.LIFE_CHANGE)


def test_namek_wilds_etb():
    _s14_assert_etb_emits("Namek Wilds", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Multicolor / mythic creatures ---

def test_goku_ssj_etb():
    _s14_assert_etb_emits("Goku, Super Saiyan", EventType.SCRY, EventType.DAMAGE)


def test_goku_ui_etb():
    _s14_assert_etb_emits("Goku, Ultra Instinct", EventType.SCRY, EventType.LIFE_CHANGE)


def test_vegeta_ssj_etb():
    _s14_assert_etb_emits("Vegeta, Super Saiyan", EventType.SURVEIL, EventType.DAMAGE)


def test_gohan_ssj2_etb():
    _s14_assert_etb_emits("Gohan, Super Saiyan 2", EventType.SCRY, EventType.DAMAGE)


def test_whis_etb():
    _s14_assert_etb_emits("Whis, Angel Attendant", EventType.SCRY, EventType.LIFE_CHANGE)


def test_jiren_etb():
    _s14_assert_etb_emits("Jiren, The Strongest", EventType.SCRY, EventType.DAMAGE)


def test_golden_frieza_etb():
    _s14_assert_etb_emits("Frieza, Golden Form", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_majin_vegeta_etb():
    _s14_assert_etb_emits("Vegeta, Majin", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_android_21_etb():
    _s14_assert_etb_emits("Android 21, Hunger Incarnate", EventType.SURVEIL, EventType.DAMAGE)


def test_kefla_etb():
    _s14_assert_etb_emits("Kefla, Potara Fusion", EventType.SCRY, EventType.DAMAGE)


def test_goku_black_etb():
    _s14_assert_etb_emits("Goku Black, Zero Mortal Plan", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_zamasu_etb():
    _s14_assert_etb_emits("Zamasu, Divine Justice", EventType.SCRY, EventType.LIFE_CHANGE)


def test_shenron_eternal_etb():
    _s14_assert_etb_emits("Shenron, Eternal Dragon", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Multicolor instants/sorceries ---

def test_kamehameha_resolve():
    _s14_assert_resolve("Kamehameha", EventType.SCRY, EventType.DAMAGE)


def test_spirit_bomb_resolve():
    _s14_assert_resolve("Spirit Bomb", EventType.SCRY, EventType.DAMAGE)


def test_destructo_disc_resolve():
    _s14_assert_resolve("Destructo Disc", EventType.SCRY, EventType.DAMAGE)


def test_death_ball_resolve():
    _s14_assert_resolve("Death Ball", EventType.SURVEIL, EventType.DAMAGE)


def test_candy_beam_resolve():
    _s14_assert_resolve("Candy Beam", EventType.SURVEIL, EventType.DISCARD)


def test_human_extinction_resolve():
    _s14_assert_resolve("Human Extinction Attack", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_solar_kamehameha_resolve():
    _s14_assert_resolve("Solar Kamehameha", EventType.SCRY, EventType.DAMAGE)


def test_final_explosion_resolve():
    _s14_assert_resolve("Final Explosion", EventType.SCRY, EventType.DAMAGE)


def test_omega_blaster_resolve():
    _s14_assert_resolve("Omega Blaster", EventType.SCRY, EventType.DAMAGE)


def test_eraser_cannon_resolve():
    _s14_assert_resolve("Eraser Cannon", EventType.SCRY, EventType.DAMAGE)


# --- Artifacts ---

def test_dragon_ball_one_etb():
    _s14_assert_etb_emits("One-Star Dragon Ball", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_two_etb():
    _s14_assert_etb_emits("Two-Star Dragon Ball", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_three_etb():
    _s14_assert_etb_emits("Three-Star Dragon Ball", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_four_etb():
    _s14_assert_etb_emits("Four-Star Dragon Ball", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_five_etb():
    _s14_assert_etb_emits("Five-Star Dragon Ball", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_six_etb():
    _s14_assert_etb_emits("Six-Star Dragon Ball", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_ball_seven_etb():
    _s14_assert_etb_emits("Seven-Star Dragon Ball", EventType.SCRY, EventType.LIFE_CHANGE)


def test_senzu_bean_etb():
    _s14_assert_etb_emits("Senzu Bean", EventType.SCRY, EventType.LIFE_CHANGE)


def test_scouter_etb():
    _s14_assert_etb_emits("Scouter", EventType.SCRY, EventType.REVEAL_HAND)


def test_potara_etb():
    _s14_assert_etb_emits("Potara Earrings", EventType.SCRY, EventType.LIFE_CHANGE)


def test_fusion_earrings_etb():
    _s14_assert_etb_emits("Fusion Earrings", EventType.SCRY, EventType.LIFE_CHANGE)


def test_gravity_chamber_etb():
    _s14_assert_etb_emits("Gravity Chamber", EventType.SCRY, EventType.LIFE_CHANGE)


def test_time_machine_etb():
    _s14_assert_etb_emits("Time Machine", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_capsule_etb():
    _s14_assert_etb_emits("Capsule", EventType.SCRY, EventType.LIFE_CHANGE)


def test_space_pod_etb():
    _s14_assert_etb_emits("Saiyan Space Pod", EventType.SCRY, EventType.DAMAGE)


def test_nimbus_etb():
    _s14_assert_etb_emits("Nimbus Cloud", EventType.SCRY, EventType.LIFE_CHANGE)


def test_dragon_radar_etb():
    _s14_assert_etb_emits("Dragon Radar", EventType.SCRY, EventType.LIFE_CHANGE)


def test_z_sword_etb():
    _s14_assert_etb_emits("Z-Sword", EventType.SCRY, EventType.DAMAGE)


def test_power_pole_etb():
    _s14_assert_etb_emits("Power Pole", EventType.SCRY, EventType.DAMAGE)


def test_turtle_shell_etb():
    _s14_assert_etb_emits("Turtle Shell", EventType.SCRY, EventType.LIFE_CHANGE)


def test_weighted_clothing_etb():
    _s14_assert_etb_emits("Weighted Clothing", EventType.SCRY, EventType.LIFE_CHANGE)


# --- Lands ---

def test_kame_house_etb():
    game = Game()
    p1 = game.add_player("Alice")
    obj = _put_on_battlefield(game, p1, "Kame House")
    info = _events_emitted_by(game, obj.id, EventType.SCRY)
    gains = _events_emitted_by(game, obj.id, EventType.LIFE_CHANGE)
    assert info and gains


def test_capsule_corp_land_etb():
    _s14_assert_etb_emits("Capsule Corporation", EventType.SURVEIL, EventType.MILL)


def test_hyperbolic_chamber_land_etb():
    _s14_assert_etb_emits("Hyperbolic Time Chamber", EventType.SCRY, EventType.LIFE_CHANGE)


def test_planet_namek_land_etb():
    game = Game()
    p1 = game.add_player("Alice")
    obj = _put_on_battlefield(game, p1, "Planet Namek")
    info = _events_emitted_by(game, obj.id, EventType.SCRY)
    gains = _events_emitted_by(game, obj.id, EventType.LIFE_CHANGE)
    assert info and gains


def test_planet_vegeta_etb():
    _s14_assert_etb_emits("Planet Vegeta", EventType.SCRY, EventType.DAMAGE)


def test_lookout_etb():
    game = Game()
    p1 = game.add_player("Alice")
    obj = _put_on_battlefield(game, p1, "The Lookout")
    info = _events_emitted_by(game, obj.id, EventType.SCRY)
    gains = _events_emitted_by(game, obj.id, EventType.LIFE_CHANGE)
    assert info and gains


def test_world_tournament_arena_etb():
    _s14_assert_etb_emits("World Tournament Arena", EventType.SCRY, EventType.DAMAGE)


def test_korin_tower_etb():
    game = Game()
    p1 = game.add_player("Alice")
    obj = _put_on_battlefield(game, p1, "Korin Tower")
    info = _events_emitted_by(game, obj.id, EventType.SCRY)
    gains = _events_emitted_by(game, obj.id, EventType.LIFE_CHANGE)
    assert info and gains


def test_frieza_spaceship_etb():
    _s14_assert_etb_emits("Frieza's Spaceship", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_cell_games_arena_etb():
    _s14_assert_etb_emits("Cell Games Arena", EventType.SURVEIL, EventType.DAMAGE)


def test_king_kai_planet_etb():
    game = Game()
    p1 = game.add_player("Alice")
    obj = _put_on_battlefield(game, p1, "King Kai's Planet")
    info = _events_emitted_by(game, obj.id, EventType.SCRY)
    gains = _events_emitted_by(game, obj.id, EventType.LIFE_CHANGE)
    assert info and gains


def test_serpent_road_etb():
    _s14_assert_etb_emits("Snake Way", EventType.SCRY, EventType.LIFE_CHANGE)


def test_majin_buu_house_etb():
    _s14_assert_etb_emits("Majin Buu's House", EventType.SURVEIL, EventType.LIFE_CHANGE)


def test_red_ribbon_hq_etb():
    _s14_assert_etb_emits("Red Ribbon Army HQ", EventType.SURVEIL, EventType.MILL)


def test_otherworld_arena_etb():
    game = Game()
    p1 = game.add_player("Alice")
    obj = _put_on_battlefield(game, p1, "Otherworld Tournament Arena")
    info = _events_emitted_by(game, obj.id, EventType.SCRY)
    gains = _events_emitted_by(game, obj.id, EventType.LIFE_CHANGE)
    assert info and gains


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
    # Slice 14 — median lift (160 vanilla cards lifted to depth-7)
    # White
    test_world_champion_etb()
    test_otherworld_fighter_etb()
    test_turtle_student_attack()
    test_crane_student_attack()
    test_senzu_heal_resolve()
    test_divine_protection_resolve()
    test_heroic_rescue_resolve()
    test_energy_barrier_resolve()
    test_kiai_shout_resolve()
    test_hope_of_earth_resolve()
    test_revival_resolve()
    test_dragon_ball_wish_resolve()
    test_training_complete_resolve()
    test_world_tournament_resolve()
    test_otherworld_ench_etb()
    test_kais_blessing_etb()
    # Blue
    test_android_19_etb()
    test_android_20_etb()
    test_capsule_drone_etb()
    test_repair_bot_etb()
    test_analysis_drone_etb()
    test_scientist_etb()
    test_red_ribbon_scout_etb()
    test_energy_absorber_etb()
    test_ki_sense_resolve()
    test_energy_drain_resolve()
    test_afterimage_resolve()
    test_instant_transmission_blue_resolve()
    test_photon_wave_resolve()
    test_solar_flare_resolve()
    test_android_construction_resolve()
    test_tech_advancement_resolve()
    test_energy_analysis_resolve()
    test_red_ribbon_research_resolve()
    test_infinite_energy_etb()
    test_capsule_technology_etb()
    test_energy_field_etb()
    # Black
    test_majin_buu_etb()
    test_super_buu_etb()
    test_zarbon_death()
    test_dodoria_death()
    test_ginyu_etb()
    test_recoome_etb()
    test_jeice_etb()
    test_frieza_soldier_etb()
    test_saibaman_death()
    test_cell_junior_etb()
    test_majin_minion_etb()
    test_dabura_etb()
    test_death_beam_resolve()
    test_supernova_resolve()
    test_finger_beam_resolve()
    test_absorption_resolve()
    test_vanish_resolve()
    test_majin_curse_resolve()
    test_planet_destruction_resolve()
    test_genocide_attack_resolve()
    test_raise_saibamen_resolve()
    test_resurrection_resolve()
    test_dark_energy_etb()
    # Red
    test_future_trunks_warrior_etb()
    test_saiyan_elite_etb()
    test_great_ape_etb()
    test_raging_saiyan_etb()
    test_saiyan_child_etb()
    test_saiyan_pod_pilot_etb()
    test_bardock_etb()
    test_final_flash_resolve()
    test_galick_gun_resolve()
    test_big_bang_attack_resolve()
    test_burning_attack_resolve()
    test_explosive_wave_resolve()
    test_saiyan_rage_resolve()
    test_ki_explosion_resolve()
    test_power_ball_resolve()
    test_saiyan_invasion_resolve()
    test_oozaru_rampage_resolve()
    test_zenkai_boost_resolve()
    test_battle_rage_etb()
    # Green
    test_namekian_warrior_etb()
    test_namekian_healer_etb()
    test_namekian_elder_etb()
    test_giant_namekian_etb()
    test_porunga_etb()
    test_ajisa_tree_etb()
    test_namek_fish_etb()
    test_special_beam_cannon_resolve()
    test_namek_regen_resolve()
    test_hellzone_grenade_resolve()
    test_masenko_resolve()
    test_fuse_resolve()
    test_nature_barrier_resolve()
    test_namekian_fusion_resolve()
    test_regrowth_resolve()
    test_dragon_ball_summon_resolve()
    test_planet_namek_resolve()
    test_healing_aura_etb()
    test_namek_wilds_etb()
    # Multicolor / mythic
    test_goku_ssj_etb()
    test_goku_ui_etb()
    test_vegeta_ssj_etb()
    test_gohan_ssj2_etb()
    test_whis_etb()
    test_jiren_etb()
    test_golden_frieza_etb()
    test_majin_vegeta_etb()
    test_android_21_etb()
    test_kefla_etb()
    test_goku_black_etb()
    test_zamasu_etb()
    test_shenron_eternal_etb()
    test_kamehameha_resolve()
    test_spirit_bomb_resolve()
    test_destructo_disc_resolve()
    test_death_ball_resolve()
    test_candy_beam_resolve()
    test_human_extinction_resolve()
    test_solar_kamehameha_resolve()
    test_final_explosion_resolve()
    test_omega_blaster_resolve()
    test_eraser_cannon_resolve()
    # Artifacts
    test_dragon_ball_one_etb()
    test_dragon_ball_two_etb()
    test_dragon_ball_three_etb()
    test_dragon_ball_four_etb()
    test_dragon_ball_five_etb()
    test_dragon_ball_six_etb()
    test_dragon_ball_seven_etb()
    test_senzu_bean_etb()
    test_scouter_etb()
    test_potara_etb()
    test_fusion_earrings_etb()
    test_gravity_chamber_etb()
    test_time_machine_etb()
    test_capsule_etb()
    test_space_pod_etb()
    test_nimbus_etb()
    test_dragon_radar_etb()
    test_z_sword_etb()
    test_power_pole_etb()
    test_turtle_shell_etb()
    test_weighted_clothing_etb()
    # Lands
    test_kame_house_etb()
    test_capsule_corp_land_etb()
    test_hyperbolic_chamber_land_etb()
    test_planet_namek_land_etb()
    test_planet_vegeta_etb()
    test_lookout_etb()
    test_world_tournament_arena_etb()
    test_korin_tower_etb()
    test_frieza_spaceship_etb()
    test_cell_games_arena_etb()
    test_king_kai_planet_etb()
    test_serpent_road_etb()
    test_majin_buu_house_etb()
    test_red_ribbon_hq_etb()
    test_otherworld_arena_etb()
    print("\n" + "=" * 60)
    print("ALL DBZ SPICE v2 EXPANSION TESTS PASSED!")
    print("=" * 60)
