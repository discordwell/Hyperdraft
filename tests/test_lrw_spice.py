"""
Lorwyn Custom Spice Pass Tests (Phase A1)

Validates the format-defining cards added to ``src/cards/custom/lorwyn_custom.py``
in the 2026-05-18 spice pass.

Cards covered (8):
- Oona, Queen of the Fae        (REWIRE)  Faerie anthem + end-step token engine
- Wort, Boggart Auntie          (REWIRE)  Upkeep RETURN_FROM_GRAVEYARD for Goblin
- Gaddock Teeg                  (REWIRE)  ETB opp-life-loss + Kithkin lord
- Wydwen, the Biting Gale       (REWIRE)  Combat-damage-to-player -> discard
- Aurora of Five                (NEW)     5-tribe extra-turn build-around
- Lorwyn Convocation            (NEW)     Dynamic PT tribal mythic + tutor
- The Aurora Cycle              (NEW)     Saga: tutor / 5 tokens / +2/+2+trample
- Treefolk-bough Spear          (NEW)     Equipment +X/+X (Treefolk+Forests)
"""

import os
import sys

# Worktree-portable sys.path — see spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.lorwyn_custom import (
    LORWYN_CUSTOM_CARDS,
    _aurora_cycle_chapter_i,
    _aurora_cycle_chapter_ii,
    _aurora_cycle_chapter_iii,
)


def _put_on_battlefield(game, player, card_name):
    """Mirror the Zelda / Star Wars spice test harness shape."""
    card_def = LORWYN_CUSTOM_CARDS[card_name]
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


def _put_in_graveyard(game, player, card_name):
    """Place a card directly into a player's graveyard for recursion tests."""
    card_def = LORWYN_CUSTOM_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    gy_zone_name = f'graveyard_{player.id}'
    if gy_zone_name in game.state.zones:
        gz = game.state.zones[gy_zone_name]
        if obj.id not in gz.objects:
            gz.objects.append(obj.id)
    return obj


def _emitted_types(game):
    return [e.type.name for e in game.state.event_log]


# ============================================================================
# Oona, Queen of the Fae (REWIRE)
# ============================================================================

def test_oona_queen_of_the_fae_loads():
    print("\n=== Oona, Queen of the Fae: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    oona = _put_on_battlefield(game, p1, "Oona, Queen of the Fae")
    assert oona.zone == ZoneType.BATTLEFIELD
    # Self flying via keyword grant + Faerie lord (P + T) + end-step trigger.
    assert len(oona.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors (keyword + lord PT + end-step); "
        f"got {len(oona.interceptor_ids)}"
    )
    assert has_ability(oona, 'flying', game.state)


def test_oona_anthem_buffs_other_faeries():
    """Other Faeries you control get +1/+1; non-Faeries unaffected."""
    print("\n=== Oona: anthem ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Use an existing Faerie body in the set.
    faerie = _put_on_battlefield(game, p1, "Glamermite")  # Faerie Rogue
    base_p = get_power(faerie, game.state)
    base_t = get_toughness(faerie, game.state)
    _put_on_battlefield(game, p1, "Oona, Queen of the Fae")
    new_p = get_power(faerie, game.state)
    new_t = get_toughness(faerie, game.state)
    assert new_p == base_p + 1, f"Expected Faerie power +1: {base_p}->{new_p}"
    assert new_t == base_t + 1, f"Expected Faerie toughness +1: {base_t}->{new_t}"
    print(f"  Glamermite (Faerie): {base_p}/{base_t} -> {new_p}/{new_t}")


def test_oona_does_not_buff_self():
    """Anthem says 'OTHER Faeries' — Oona herself doesn't get +1/+1."""
    print("\n=== Oona: does not self-buff ===")
    game = Game()
    p1 = game.add_player("Alice")
    oona = _put_on_battlefield(game, p1, "Oona, Queen of the Fae")
    p = get_power(oona, game.state)
    t = get_toughness(oona, game.state)
    assert p == 5, f"Expected Oona power 5 (no self-anthem); got {p}"
    assert t == 5, f"Expected Oona toughness 5 (no self-anthem); got {t}"


def test_oona_end_step_creates_faerie_token():
    """End step (controller's turn) emits a Faerie Rogue CREATE_TOKEN."""
    print("\n=== Oona: end-step token ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Oona, Queen of the Fae")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    tokens = [
        e for e in new
        if e.type == EventType.CREATE_TOKEN
        and (e.payload.get('token', {}).get('subtypes', set()) & {'Faerie'})
    ]
    assert tokens, (
        f"Expected CREATE_TOKEN with Faerie subtype; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )
    print(f"  Faerie token events: {len(tokens)}")


def test_oona_opp_end_step_no_trigger():
    """Opp's end step does not spawn a Faerie."""
    print("\n=== Oona: opp end step does not fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Oona, Queen of the Fae")
    before = len(game.state.event_log)
    game.state.active_player = p2.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    tokens = [
        e for e in new
        if e.type == EventType.CREATE_TOKEN
        and (e.payload.get('token', {}).get('subtypes', set()) & {'Faerie'})
    ]
    assert not tokens, "Oona fired on opp end step"


# ============================================================================
# Wort, Boggart Auntie (REWIRE)
# ============================================================================

def test_wort_boggart_auntie_loads():
    print("\n=== Wort, Boggart Auntie: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wort = _put_on_battlefield(game, p1, "Wort, Boggart Auntie")
    assert wort.zone == ZoneType.BATTLEFIELD
    # keyword (fear) + upkeep trigger.
    assert len(wort.interceptor_ids) >= 2
    assert has_ability(wort, 'fear', game.state)


def test_wort_upkeep_returns_goblin_from_graveyard():
    """Upkeep emits RETURN_FROM_GRAVEYARD for a Goblin in p1's GY."""
    print("\n=== Wort: upkeep -> return goblin ===")
    game = Game()
    p1 = game.add_player("Alice")
    goblin = _put_in_graveyard(game, p1, "Hovel Hurler")  # Goblin Warrior

    _put_on_battlefield(game, p1, "Wort, Boggart Auntie")
    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    returns = [
        e for e in new
        if e.type == EventType.RETURN_FROM_GRAVEYARD
        and e.payload.get('object_id') == goblin.id
        and e.payload.get('destination') == 'hand'
    ]
    assert returns, (
        f"Expected RETURN_FROM_GRAVEYARD for Goblin {goblin.id}; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_wort_empty_graveyard_no_return():
    """Empty graveyard -> no RETURN_FROM_GRAVEYARD events."""
    print("\n=== Wort: empty graveyard ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Wort, Boggart Auntie")
    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    returns = [e for e in new if e.type == EventType.RETURN_FROM_GRAVEYARD]
    assert not returns, f"Expected no returns with empty GY; got {len(returns)}"


def test_wort_opp_upkeep_no_trigger():
    """Opp's upkeep doesn't fire Wort's return."""
    print("\n=== Wort: opp upkeep ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_in_graveyard(game, p1, "Hovel Hurler")
    _put_on_battlefield(game, p1, "Wort, Boggart Auntie")

    before = len(game.state.event_log)
    game.state.active_player = p2.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    returns = [e for e in new if e.type == EventType.RETURN_FROM_GRAVEYARD]
    assert not returns, "Wort fired on opp upkeep"


# ============================================================================
# Gaddock Teeg (REWIRE)
# ============================================================================

def test_gaddock_teeg_loads():
    print("\n=== Gaddock Teeg: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    teeg = _put_on_battlefield(game, p1, "Gaddock Teeg")
    assert teeg.zone == ZoneType.BATTLEFIELD
    # Anthem PT (2 interceptors) + ETB trigger.
    assert len(teeg.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors (lord PT + ETB); got {len(teeg.interceptor_ids)}"
    )


def test_gaddock_teeg_etb_drains_opponents():
    """ETB emits LIFE_CHANGE -2 for each opponent."""
    print("\n=== Gaddock Teeg: ETB drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Gaddock Teeg")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -2
    ]
    assert drains, f"Expected -2 LIFE_CHANGE on opp; got {len(drains)}"


def test_gaddock_teeg_anthem_other_kithkin():
    """Other Kithkin you control get +1/+1."""
    print("\n=== Gaddock Teeg: Kithkin anthem ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Use an existing Kithkin (Brigid, Clachan's Heart).
    kithkin = _put_on_battlefield(game, p1, "Brigid, Clachan's Heart")
    base_p = get_power(kithkin, game.state)
    _put_on_battlefield(game, p1, "Gaddock Teeg")
    new_p = get_power(kithkin, game.state)
    assert new_p == base_p + 1, f"Expected Kithkin +1 power: {base_p}->{new_p}"


# ============================================================================
# Wydwen, the Biting Gale (REWIRE)
# ============================================================================

def test_wydwen_loads_with_keywords():
    """Setup registers self flash+flying via keyword_grant + damage trigger."""
    print("\n=== Wydwen: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wyd = _put_on_battlefield(game, p1, "Wydwen, the Biting Gale")
    assert wyd.zone == ZoneType.BATTLEFIELD
    assert has_ability(wyd, 'flying', game.state)
    assert has_ability(wyd, 'flash', game.state)


def test_wydwen_combat_damage_to_player_discards():
    """When Wydwen deals combat damage to a player, that player discards."""
    print("\n=== Wydwen: combat damage -> discard ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    wyd = _put_on_battlefield(game, p1, "Wydwen, the Biting Gale")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': wyd.id,
            'target': p2.id,
            'amount': 3,
            'is_combat': True,
        },
        source=wyd.id,
    ))
    new = game.state.event_log[before:]
    discards = [
        e for e in new
        if e.type == EventType.DISCARD and e.payload.get('player') == p2.id
    ]
    assert discards, (
        f"Expected DISCARD on combat damage to p2; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_wydwen_noncombat_damage_no_discard():
    """Noncombat damage does not trigger the discard."""
    print("\n=== Wydwen: noncombat damage -> no discard ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    wyd = _put_on_battlefield(game, p1, "Wydwen, the Biting Gale")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': wyd.id,
            'target': p2.id,
            'amount': 3,
            'is_combat': False,
        },
        source=wyd.id,
    ))
    new = game.state.event_log[before:]
    discards = [
        e for e in new
        if e.type == EventType.DISCARD and e.payload.get('player') == p2.id
    ]
    assert not discards, "Wydwen fired on noncombat damage"


# ============================================================================
# Aurora of Five (NEW build-around)
# ============================================================================

def test_aurora_of_five_loads():
    print("\n=== Aurora of Five: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    aurora = _put_on_battlefield(game, p1, "Aurora of Five")
    assert aurora.zone == ZoneType.BATTLEFIELD
    assert aurora.interceptor_ids, "Expected an upkeep trigger"


def test_aurora_of_five_upkeep_no_tribes_scry2():
    """Without enough tribes, upkeep emits SCRY 2 (not EXTRA_TURN)."""
    print("\n=== Aurora of Five: upkeep -> scry (no assembly) ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Aurora of Five")
    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    extra = [e for e in new if e.type == EventType.EXTRA_TURN]
    scry = [
        e for e in new
        if e.type == EventType.SCRY and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 2
    ]
    assert not extra, "Should not take EXTRA_TURN with 0 tribes"
    assert scry, f"Expected SCRY 2 fallback; recent={[e.type.name for e in new[-10:]]}"


def test_aurora_of_five_upkeep_five_tribes_extra_turn():
    """With 5+ distinct Lorwyn tribes assembled, upkeep emits EXTRA_TURN."""
    print("\n=== Aurora of Five: upkeep -> extra turn (5 tribes) ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Assemble 5 tribes: Faerie + Kithkin + Treefolk + Elf + Merfolk.
    _put_on_battlefield(game, p1, "Glamermite")           # Faerie Rogue
    _put_on_battlefield(game, p1, "Brigid, Clachan's Heart")  # Kithkin Warrior
    _put_on_battlefield(game, p1, "Treefolk Harbinger")    # Treefolk Druid
    _put_on_battlefield(game, p1, "Heritage Druid")        # Elf Druid
    _put_on_battlefield(game, p1, "Mulldrifter")           # Merfolk (in set)

    _put_on_battlefield(game, p1, "Aurora of Five")

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
    assert extra, (
        f"Expected EXTRA_TURN with 5 tribes assembled; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_aurora_of_five_four_tribes_no_extra_turn():
    """Four tribes is below the gate — still SCRY 2, no EXTRA_TURN."""
    print("\n=== Aurora of Five: 4 tribes is below threshold ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Glamermite")
    _put_on_battlefield(game, p1, "Brigid, Clachan's Heart")
    _put_on_battlefield(game, p1, "Treefolk Harbinger")
    _put_on_battlefield(game, p1, "Heritage Druid")

    _put_on_battlefield(game, p1, "Aurora of Five")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    extra = [e for e in new if e.type == EventType.EXTRA_TURN]
    assert not extra, "Should not take extra turn at 4 tribes"


# ============================================================================
# Lorwyn Convocation (NEW)
# ============================================================================

def test_lorwyn_convocation_loads():
    print("\n=== Lorwyn Convocation: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    lc = _put_on_battlefield(game, p1, "Lorwyn Convocation")
    # Two PT QUERY interceptors + one ETB.
    assert len(lc.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors; got {len(lc.interceptor_ids)}"
    )


def test_lorwyn_convocation_etb_tutors_creature():
    """ETB emits SEARCH_LIBRARY for a creature card."""
    print("\n=== Lorwyn Convocation: ETB tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Lorwyn Convocation")
    new = game.state.event_log[before:]
    searches = [
        e for e in new
        if e.type == EventType.SEARCH_LIBRARY
        and e.payload.get('card_type') == 'creature'
        and e.payload.get('destination') == 'hand'
    ]
    assert searches, (
        f"Expected SEARCH_LIBRARY for creature; recent={[e.type.name for e in new[-10:]]}"
    )


def test_lorwyn_convocation_scales_with_tribes():
    """+1/+1 for each different tribe (of the 5) on the battlefield."""
    print("\n=== Lorwyn Convocation: PT scales with tribes ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Convocation itself counts as a Treefolk (+1 base tribe).
    lc = _put_on_battlefield(game, p1, "Lorwyn Convocation")
    base_p = lc.characteristics.power  # 4
    # With only Convocation (Treefolk), one tribe is present. +1/+1.
    p = get_power(lc, game.state)
    assert p == base_p + 1, f"Expected base+1 (Treefolk only): {base_p}->{p}"

    # Add a Faerie.
    _put_on_battlefield(game, p1, "Glamermite")  # Faerie
    p = get_power(lc, game.state)
    assert p == base_p + 2, f"Expected base+2 (Treefolk+Faerie): {base_p}->{p}"

    # Add a Kithkin.
    _put_on_battlefield(game, p1, "Brigid, Clachan's Heart")  # Kithkin
    p = get_power(lc, game.state)
    assert p == base_p + 3, f"Expected base+3: {base_p}->{p}"
    print(f"  Lorwyn Convocation power with 3 tribes: {p}")


# ============================================================================
# The Aurora Cycle (NEW saga)
# ============================================================================

def test_the_aurora_cycle_loads_saga():
    print("\n=== The Aurora Cycle: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Aurora Cycle")
    assert saga.interceptor_ids, "Saga should register chapter interceptors"


def test_the_aurora_cycle_chapter_i_emits_elemental_tutor():
    """Chapter I: SEARCH_LIBRARY for Elemental creature -> hand."""
    print("\n=== The Aurora Cycle: chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Aurora Cycle")
    events = _aurora_cycle_chapter_i(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert payload.get('subtype') == 'Elemental'
    assert payload.get('card_type') == 'creature'
    assert payload.get('destination') == 'hand'


def test_the_aurora_cycle_chapter_ii_creates_five_tribe_tokens():
    """Chapter II: 5 distinct tribe tokens (Faerie, Kithkin, Treefolk, Goblin, Merfolk)."""
    print("\n=== The Aurora Cycle: chapter II ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Aurora Cycle")
    events = _aurora_cycle_chapter_ii(saga, game.state)
    tokens = [e for e in events if e.type == EventType.CREATE_TOKEN]
    assert len(tokens) == 5, f"Expected 5 tribe tokens; got {len(tokens)}"
    # Verify the set of tribes covered.
    found_tribes: set[str] = set()
    for e in tokens:
        subs = e.payload.get('token', {}).get('subtypes', set())
        for tribe in ('Faerie', 'Kithkin', 'Treefolk', 'Goblin', 'Merfolk'):
            if tribe in subs:
                found_tribes.add(tribe)
    assert found_tribes == {'Faerie', 'Kithkin', 'Treefolk', 'Goblin', 'Merfolk'}, (
        f"Wrong tribes; got {found_tribes}"
    )


def test_the_aurora_cycle_chapter_iii_pumps_other_creatures():
    """Chapter III: every other creature you control gets +2/+2 + trample."""
    print("\n=== The Aurora Cycle: chapter III ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Aurora Cycle")
    glamermite = _put_on_battlefield(game, p1, "Glamermite")

    events = _aurora_cycle_chapter_iii(saga, game.state)
    pumped = [
        e for e in events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == glamermite.id
        and e.payload.get('power_mod') == 2
        and e.payload.get('toughness_mod') == 2
    ]
    assert pumped, f"Expected PT_MOD +2/+2 on Glamermite; events: {events}"
    trample_grants = [
        e for e in events
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == glamermite.id
        and e.payload.get('keyword') == 'trample'
    ]
    assert trample_grants, "Expected trample grant on Glamermite"
    # Saga should NOT pump itself (chapter III excludes the source).
    saga_pumps = [
        e for e in events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == saga.id
    ]
    assert not saga_pumps, "Saga should not pump itself"


# ============================================================================
# Treefolk-bough Spear (NEW Equipment)
# ============================================================================

def test_treefolk_bough_spear_loads():
    print("\n=== Treefolk-bough Spear: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    spear = _put_on_battlefield(game, p1, "Treefolk-bough Spear")
    assert spear.zone == ZoneType.BATTLEFIELD
    # make_equipment_setup + 2 dynamic PT interceptors.
    activated = getattr(spear.state, 'activated_abilities', None)
    assert activated, "Expected an equip ability"


def test_treefolk_bough_spear_attach_scales_with_treefolk():
    """ATTACH boosts equipped creature by Treefolk + Forests count."""
    print("\n=== Treefolk-bough Spear: attach scales ===")
    game = Game()
    p1 = game.add_player("Alice")
    spear = _put_on_battlefield(game, p1, "Treefolk-bough Spear")
    # Pick a non-Treefolk to make the math easy.
    knight = _put_on_battlefield(game, p1, "Brigid, Clachan's Heart")  # Kithkin Warrior 3/2
    base_p = knight.characteristics.power
    base_t = knight.characteristics.toughness

    # Attach the spear.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': spear.id, 'target_id': knight.id},
        source=spear.id,
    ))

    # With 0 Treefolk + 0 Forests, +0/+0.
    p0 = get_power(knight, game.state)
    t0 = get_toughness(knight, game.state)
    assert p0 == base_p, f"With 0 Treefolk/Forest, no buff: {base_p}->{p0}"

    # Add a Treefolk.
    _put_on_battlefield(game, p1, "Treefolk Harbinger")  # Treefolk Druid
    p1_val = get_power(knight, game.state)
    t1_val = get_toughness(knight, game.state)
    assert p1_val == base_p + 1, f"With 1 Treefolk, +1: {base_p}->{p1_val}"
    assert t1_val == base_t + 1, f"With 1 Treefolk, +1: {base_t}->{t1_val}"

    # Add another Treefolk -> +2/+2.
    _put_on_battlefield(game, p1, "Timber Protector")  # Treefolk Warrior
    p2_val = get_power(knight, game.state)
    assert p2_val == base_p + 2, f"With 2 Treefolk, +2: {base_p}->{p2_val}"
    print(f"  Brigid {base_p}/{base_t} -> {p2_val}/{t1_val + 1} with 2 Treefolk equipped")


def test_treefolk_bough_spear_unattached_no_buff():
    """Without ATTACH, no creature is buffed (PT query no-op)."""
    print("\n=== Treefolk-bough Spear: unequipped ===")
    game = Game()
    p1 = game.add_player("Alice")
    spear = _put_on_battlefield(game, p1, "Treefolk-bough Spear")
    knight = _put_on_battlefield(game, p1, "Brigid, Clachan's Heart")
    _put_on_battlefield(game, p1, "Treefolk Harbinger")

    base_p = knight.characteristics.power
    p = get_power(knight, game.state)
    # No ATTACH event -> spear.state.attached_to is None -> no buff.
    assert p == base_p, f"Expected no buff while unattached: {base_p}->{p}"


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
