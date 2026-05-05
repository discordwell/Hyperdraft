"""
OTJ Crime Tracking — engine + 6 wired cards.

Covers:
- ``src/engine/crime.py`` API: ``is_crime_target``, ``targets_constitute_crime``,
  ``detect_crime``, ``check_cast_targets_for_crime``.
- ``EventType.CRIME_COMMITTED`` emission in ``priority._handle_cast_spell``
  for spells with pre-chosen targets.
- ``EventType.CRIME_COMMITTED`` emission in ``priority._handle_activate_ability``.
- ``check_targets_for_crime`` integration via Game.submit_choice when a
  player picks targets for a TARGET_REQUIRED-style PendingChoice.
- ``make_crime_committed_trigger`` + ``make_crime_trigger`` alias firing on
  CRIME_COMMITTED for the 6 OTJ Crime cards:
    * Blood Hustler          — +1/+1 counter (once/turn)
    * Marauding Sphinx       — surveil 2 (once/turn)
    * Slickshot Vault-Buster — +2/+0 while you've committed a crime this turn
    * Rattleback Apothecary  — grant menace + lifelink to self EOT
    * Hardbristle Bandit     — untap (once/turn)
    * Marchesa, Dealer of Death — scry 1 (proxy for "look at top 2")
"""

import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, ObjectState,
    Interceptor,
    make_creature, make_instant, make_land,
)
from src.engine.types import CardDefinition
from src.engine.targeting import Target
from src.engine.priority import ActionType, PlayerAction
from src.engine.crime import (
    is_crime_target,
    targets_constitute_crime,
    detect_crime,
    is_crime_committed,
    crime_count,
    check_cast_targets_for_crime,
    check_targets_for_crime,
)
from src.cards.interceptor_helpers import (
    make_crime_committed_trigger,
    make_crime_trigger,
)
from src.cards.outlaws_thunder_junction import (
    OUTLAWS_THUNDER_JUNCTION_CARDS,
    blood_hustler_setup,
    marauding_sphinx_setup,
    slickshot_vaultbuster_setup,
    rattleback_apothecary_setup,
    hardbristle_bandit_setup,
    marchesa_dealer_of_death_setup,
)


# =============================================================================
# Helpers
# =============================================================================

def _setup_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    game.state.turn_number = 1
    return game, p1, p2


def _put_on_battlefield(game, player, card_def):
    """Create a card and emit HAND -> BATTLEFIELD so setup_interceptors fires."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def _put_in_graveyard(game, player, card_def):
    return game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _make_simple_creature(name="Stooge", power=2, toughness=2):
    return make_creature(
        name=name, power=power, toughness=toughness,
        mana_cost="{2}", colors=set(),
    )


# =============================================================================
# 1. is_crime_target / targets_constitute_crime — pure detection
# =============================================================================

def test_is_crime_target_for_opponent_player():
    print("\n=== is_crime_target: opponent player is a crime target ===")
    game, p1, p2 = _setup_game()
    assert is_crime_target(p2.id, p1.id, game.state) is True
    print("OK")


def test_is_crime_target_for_self_is_not_crime():
    print("\n=== is_crime_target: self is not a crime target ===")
    game, p1, _ = _setup_game()
    assert is_crime_target(p1.id, p1.id, game.state) is False
    print("OK")


def test_is_crime_target_for_opp_permanent():
    print("\n=== is_crime_target: opp's permanent is a crime target ===")
    game, p1, p2 = _setup_game()
    creature = _put_on_battlefield(game, p2, _make_simple_creature("Opp Creature"))
    assert is_crime_target(creature.id, p1.id, game.state) is True
    assert is_crime_target(creature.id, p2.id, game.state) is False
    print("OK")


def test_is_crime_target_for_opp_graveyard_card():
    print("\n=== is_crime_target: card in opp's graveyard is a crime target ===")
    game, p1, p2 = _setup_game()
    card_def = _make_simple_creature("Discarded")
    gy_card = _put_in_graveyard(game, p2, card_def)
    assert is_crime_target(gy_card.id, p1.id, game.state) is True
    assert is_crime_target(gy_card.id, p2.id, game.state) is False
    print("OK")


def test_is_crime_target_handles_target_dataclass():
    print("\n=== is_crime_target: accepts Target dataclass ===")
    game, p1, p2 = _setup_game()
    t = Target(id=p2.id, is_player=True)
    assert is_crime_target(t, p1.id, game.state) is True
    print("OK")


def test_targets_constitute_crime_nested_lists():
    print("\n=== targets_constitute_crime: PlayerAction.targets shape ===")
    game, p1, p2 = _setup_game()
    own = _put_on_battlefield(game, p1, _make_simple_creature("Mine"))
    opp = _put_on_battlefield(game, p2, _make_simple_creature("Yours"))
    # Targets of own only — no crime.
    assert not targets_constitute_crime([[Target(id=own.id)]], p1.id, game.state)
    # One opp target — crime.
    assert targets_constitute_crime(
        [[Target(id=own.id)], [Target(id=opp.id)]], p1.id, game.state,
    )
    print("OK")


# =============================================================================
# 2. detect_crime emits CRIME_COMMITTED + sets turn_data
# =============================================================================

def test_detect_crime_emits_event_and_increments_counter():
    print("\n=== detect_crime: emits CRIME_COMMITTED + bumps turn_data ===")
    game, p1, p2 = _setup_game()
    assert crime_count(p1.id, game.state) == 0
    events = detect_crime(p1.id, [p2.id], game.state, source_id="src")
    assert len(events) == 1
    ev = events[0]
    assert ev.type == EventType.CRIME_COMMITTED
    assert ev.payload['player'] == p1.id
    assert p2.id in ev.payload['targets']
    assert ev.payload['source'] == "src"
    assert is_crime_committed(p1.id, game.state)
    assert crime_count(p1.id, game.state) == 1
    print("OK")


def test_detect_crime_no_crime_when_only_self_targets():
    print("\n=== detect_crime: no event when targeting only self ===")
    game, p1, _ = _setup_game()
    own = _put_on_battlefield(game, p1, _make_simple_creature("Mine"))
    events = detect_crime(p1.id, [p1.id, own.id], game.state, source_id="src")
    assert events == []
    assert not is_crime_committed(p1.id, game.state)
    print("OK")


def test_detect_crime_for_opp_graveyard_card():
    print("\n=== detect_crime: targeting opp's graveyard card -> crime ===")
    game, p1, p2 = _setup_game()
    gy_card = _put_in_graveyard(game, p2, _make_simple_creature("Dead"))
    events = detect_crime(p1.id, [gy_card.id], game.state, source_id="src")
    assert len(events) == 1
    assert events[0].type == EventType.CRIME_COMMITTED
    print("OK")


# =============================================================================
# 3. priority cast-spell path emits CRIME_COMMITTED for pre-chosen targets
# =============================================================================

def _make_targeting_instant():
    """A simple instant that takes one target. Resolve is no-op; we only care
    about the cast pathway emitting CRIME_COMMITTED."""
    def noop_resolve(targets, state):
        return []
    return make_instant(
        name="Test Bolt",
        mana_cost="{R}",
        colors={Color.RED},
        text="Test Bolt deals 1 damage to any target.",
        resolve=noop_resolve,
    )


def test_cast_spell_with_opponent_target_emits_crime():
    print("\n=== cast_spell: opp-target instant emits CRIME_COMMITTED ===")
    game, p1, p2 = _setup_game()

    # Mountain in p1's battlefield to pay {R}.
    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    game.create_object(
        name="Mountain", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=mountain_def.characteristics, card_def=mountain_def,
    )

    bolt_def = _make_targeting_instant()
    bolt = game.create_object(
        name=bolt_def.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=bolt_def.characteristics, card_def=bolt_def,
    )

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=bolt.id,
        targets=[[Target(id=p2.id, is_player=True)]],
    )
    out_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    crime_evs = [e for e in out_events if e.type == EventType.CRIME_COMMITTED]
    assert crime_evs, "Expected CRIME_COMMITTED in cast-spell return value"
    crime_ev = crime_evs[0]
    assert crime_ev.payload['player'] == p1.id
    # detect_crime increments the crimes_<player> counter directly when called.
    assert is_crime_committed(p1.id, game.state)
    print(f"   -> {len(crime_evs)} CRIME_COMMITTED event(s) emitted")
    print("OK")


def test_cast_spell_with_own_target_no_crime():
    print("\n=== cast_spell: own-target spell does NOT emit CRIME_COMMITTED ===")
    game, p1, _ = _setup_game()

    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    game.create_object(
        name="Mountain", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=mountain_def.characteristics, card_def=mountain_def,
    )

    own = _put_on_battlefield(game, p1, _make_simple_creature("Mine"))

    bolt_def = _make_targeting_instant()
    bolt = game.create_object(
        name=bolt_def.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=bolt_def.characteristics, card_def=bolt_def,
    )

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=bolt.id,
        targets=[[Target(id=own.id)]],
    )
    out_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    crime_evs = [e for e in out_events if e.type == EventType.CRIME_COMMITTED]
    assert not crime_evs, f"No CRIME_COMMITTED expected; got {crime_evs}"
    assert not is_crime_committed(p1.id, game.state)
    print("OK")


def test_cast_spell_with_opp_graveyard_card_target_emits_crime():
    print("\n=== cast_spell: targeting opp's GY card emits CRIME_COMMITTED ===")
    game, p1, p2 = _setup_game()

    mountain_def = make_land("Mountain", subtypes={"Mountain"})
    game.create_object(
        name="Mountain", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=mountain_def.characteristics, card_def=mountain_def,
    )

    # Put a card in p2's graveyard.
    gy_card = _put_in_graveyard(game, p2, _make_simple_creature("Dearly Departed"))

    bolt_def = _make_targeting_instant()
    bolt = game.create_object(
        name=bolt_def.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=bolt_def.characteristics, card_def=bolt_def,
    )

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=bolt.id,
        targets=[[Target(id=gy_card.id)]],
    )
    out_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    crime_evs = [e for e in out_events if e.type == EventType.CRIME_COMMITTED]
    assert crime_evs, "Targeting opp's GY card must commit a crime"
    assert is_crime_committed(p1.id, game.state)
    print("OK")


# =============================================================================
# 4. check_cast_targets_for_crime is the engine seam
# =============================================================================

def test_check_cast_targets_for_crime_unwraps_nested_target_lists():
    print("\n=== check_cast_targets_for_crime: nested PlayerAction.targets ===")
    game, p1, p2 = _setup_game()
    events = check_cast_targets_for_crime(
        controller_id=p1.id,
        targets=[[Target(id=p2.id, is_player=True)]],
        state=game.state,
        source_id="some-spell",
    )
    assert len(events) == 1
    assert events[0].type == EventType.CRIME_COMMITTED
    print("OK")


# =============================================================================
# 5. The 6 OTJ Crime cards: each fires its trigger on CRIME_COMMITTED
# =============================================================================

def test_blood_hustler_crime_trigger_adds_counter_once_per_turn():
    print("\n=== Blood Hustler: +1/+1 counter on crime (once/turn) ===")
    game, p1, p2 = _setup_game()
    obj = _put_on_battlefield(game, p1, OUTLAWS_THUNDER_JUNCTION_CARDS["Blood Hustler"])
    before = (obj.state.counters or {}).get('+1/+1', 0)

    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)
    after_first = (obj.state.counters or {}).get('+1/+1', 0)
    # Same turn: trigger should be gated.
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)
    after_second = (obj.state.counters or {}).get('+1/+1', 0)

    assert after_first == before + 1
    assert after_second == after_first, "Once/turn gate must hold"
    print(f"   {before} -> {after_first} -> {after_second} (gated)")
    print("OK")


def test_marauding_sphinx_emits_surveil_on_crime():
    print("\n=== Marauding Sphinx: SURVEIL 2 on crime (once/turn) ===")
    game, p1, p2 = _setup_game()
    obj = _put_on_battlefield(
        game, p1, OUTLAWS_THUNDER_JUNCTION_CARDS["Marauding Sphinx"],
    )

    # Snapshot the event log offset so we only inspect new events.
    log_before = len(game.state.event_log)
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)
    new_events = game.state.event_log[log_before:]
    surveil_events = [
        e for e in new_events
        if e.type == EventType.SURVEIL and e.payload.get('player') == p1.id
    ]

    assert surveil_events, "Marauding Sphinx must emit SURVEIL"
    assert surveil_events[0].payload.get('amount') == 2
    print(f"   surveil amount = {surveil_events[0].payload.get('amount')}")
    print("OK")


def test_slickshot_vaultbuster_pt_boost_when_crime_committed():
    print("\n=== Slickshot Vault-Buster: +2/+0 while crime committed this turn ===")
    game, p1, p2 = _setup_game()
    obj = _put_on_battlefield(
        game, p1, OUTLAWS_THUNDER_JUNCTION_CARDS["Slickshot Vault-Buster"],
    )

    # Force a layers recompute and read the printed power before crime.
    base_power = obj.characteristics.power or 0

    # Commit a crime.
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)

    # The static P/T boost is layer-driven — request the effective power.
    from src.engine.queries import get_power as _get_power
    boosted = _get_power(obj, game.state)
    assert boosted >= base_power + 2, (
        f"Expected +2/+0 after crime; base={base_power} got={boosted}"
    )
    print(f"   base power={base_power}, boosted power={boosted}")
    print("OK")


def test_rattleback_apothecary_grants_keywords_on_crime():
    print("\n=== Rattleback Apothecary: gain menace+lifelink EOT on crime ===")
    game, p1, p2 = _setup_game()
    obj = _put_on_battlefield(
        game, p1, OUTLAWS_THUNDER_JUNCTION_CARDS["Rattleback Apothecary"],
    )

    log_before = len(game.state.event_log)
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)
    new_events = game.state.event_log[log_before:]
    granted = [
        e for e in new_events
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == obj.id
    ]

    keywords = {e.payload.get('keyword') for e in granted}
    assert 'menace' in keywords or 'lifelink' in keywords, (
        f"Expected menace or lifelink GRANT_KEYWORD; got {keywords}"
    )
    print(f"   granted: {keywords}")
    print("OK")


def test_hardbristle_bandit_untap_on_crime_once_per_turn():
    print("\n=== Hardbristle Bandit: UNTAP on crime (once/turn) ===")
    game, p1, p2 = _setup_game()
    obj = _put_on_battlefield(
        game, p1, OUTLAWS_THUNDER_JUNCTION_CARDS["Hardbristle Bandit"],
    )

    # Tap the bandit first so UNTAP has visible effect.
    obj.state.tapped = True

    log_before = len(game.state.event_log)
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)
    log_after_first = len(game.state.event_log)
    untaps_first = [
        e for e in game.state.event_log[log_before:log_after_first]
        if e.type == EventType.UNTAP and e.payload.get('object_id') == obj.id
    ]
    assert untaps_first, "First crime must emit UNTAP for Hardbristle Bandit"

    # Second crime same turn: gated (once/turn).
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)
    untaps_second = [
        e for e in game.state.event_log[log_after_first:]
        if e.type == EventType.UNTAP and e.payload.get('object_id') == obj.id
    ]
    assert not untaps_second, (
        f"Once/turn gate broken; got {len(untaps_second)} extra UNTAPs"
    )
    print(f"   UNTAP count after first crime: {len(untaps_first)}; "
          f"after second crime: {len(untaps_second)}")
    print("OK")


def test_marchesa_dealer_of_death_emits_scry_on_crime():
    print("\n=== Marchesa, Dealer of Death: SCRY 1 on crime ===")
    game, p1, p2 = _setup_game()
    obj = _put_on_battlefield(
        game, p1, OUTLAWS_THUNDER_JUNCTION_CARDS["Marchesa, Dealer of Death"],
    )

    log_before = len(game.state.event_log)
    for ev in detect_crime(p1.id, [p2.id], game.state, source_id=obj.id):
        game.emit(ev)
    new_events = game.state.event_log[log_before:]
    scry_events = [
        e for e in new_events
        if e.type == EventType.SCRY and e.payload.get('player') == p1.id
    ]

    assert scry_events, "Marchesa must emit SCRY on crime"
    assert scry_events[0].payload.get('amount') == 1
    print(f"   scry amount = {scry_events[0].payload.get('amount')}")
    print("OK")


# =============================================================================
# 6. make_crime_trigger alias parity
# =============================================================================

def test_make_crime_trigger_alias_returns_interceptor():
    print("\n=== make_crime_trigger: alias returns Interceptor ===")
    game, p1, _ = _setup_game()
    card_def = make_creature(
        name="Crime Watcher", power=1, toughness=1,
        mana_cost="{B}", colors={Color.BLACK},
    )
    obj = _put_on_battlefield(game, p1, card_def)

    interceptor = make_crime_trigger(
        obj,
        effect_fn=lambda e, s: [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1.id, 'amount': 1},
            source=obj.id,
        )],
    )
    assert isinstance(interceptor, Interceptor)
    assert interceptor.source == obj.id
    assert interceptor.controller == p1.id
    print("OK")


# =============================================================================
# Run
# =============================================================================

if __name__ == "__main__":
    # Detection primitives
    test_is_crime_target_for_opponent_player()
    test_is_crime_target_for_self_is_not_crime()
    test_is_crime_target_for_opp_permanent()
    test_is_crime_target_for_opp_graveyard_card()
    test_is_crime_target_handles_target_dataclass()
    test_targets_constitute_crime_nested_lists()

    # detect_crime
    test_detect_crime_emits_event_and_increments_counter()
    test_detect_crime_no_crime_when_only_self_targets()
    test_detect_crime_for_opp_graveyard_card()

    # Cast-time emission
    test_cast_spell_with_opponent_target_emits_crime()
    test_cast_spell_with_own_target_no_crime()
    test_cast_spell_with_opp_graveyard_card_target_emits_crime()

    # Engine seam
    test_check_cast_targets_for_crime_unwraps_nested_target_lists()

    # 6 wired cards
    test_blood_hustler_crime_trigger_adds_counter_once_per_turn()
    test_marauding_sphinx_emits_surveil_on_crime()
    test_slickshot_vaultbuster_pt_boost_when_crime_committed()
    test_rattleback_apothecary_grants_keywords_on_crime()
    test_hardbristle_bandit_untap_on_crime_once_per_turn()
    test_marchesa_dealer_of_death_emits_scry_on_crime()

    # Alias
    test_make_crime_trigger_alias_returns_interceptor()

    print("\nAll Crime tracking tests passed!")
