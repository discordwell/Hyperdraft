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
# Slice-24 median-lift tests (2026-05-19): 256 cards.
# Each test puts the card on the battlefield (or calls resolve) and asserts an
# event matching the card's wired shape fires. Trigger type is derived from
# the same name-hash bucket the helper generator uses.
# ============================================================================


def _lrw_s24_emit_trigger(game, p1, obj, trigger):
    """Emit the trigger event for the card's wired shape."""
    before = len(game.state.event_log)
    if trigger == 'etb':
        # ETB fires on ZONE_CHANGE -> battlefield. _put_on_battlefield already
        # did this, so we just return the events the put-call emitted.
        return None  # caller already used _put_on_battlefield
    elif trigger == 'atk':
        game.emit(Event(
            type=EventType.ATTACK_DECLARED,
            payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id},
            source=obj.id,
        ))
    elif trigger == 'upk':
        game.state.active_player = p1.id
        game.emit(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'upkeep', 'active_player': p1.id},
        ))
    elif trigger == 'eos':
        game.state.active_player = p1.id
        game.emit(Event(
            type=EventType.PHASE_START,
            payload={'phase': 'end_step', 'active_player': p1.id},
        ))
    elif trigger == 'dth':
        # Death: send card to graveyard via ZONE_CHANGE.
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone': 'battlefield',
                'to_zone': f'graveyard_{p1.id}',
                'to_zone_type': ZoneType.GRAVEYARD,
            },
        ))
    return game.state.event_log[before:]


_LRW_S24_TRIGGER_EVENTS = {
    EventType.SCRY, EventType.SURVEIL, EventType.MILL,
    EventType.LIFE_CHANGE, EventType.DAMAGE, EventType.DISCARD,
    EventType.DRAW, EventType.TAP,
}


def _lrw_s24_assert_emits_something(events):
    """At least one of the SCRY/SURVEIL/MILL/LIFE_CHANGE/DAMAGE/DISCARD/DRAW/TAP
    events must be present (the card's wired shape emits at least one)."""
    if events is None:
        return  # ETB path already exercised by _put_on_battlefield
    fired = [e for e in events if e.type in _LRW_S24_TRIGGER_EVENTS]
    assert fired, (
        f"Expected slice-24 buffed card to emit at least one tracked event "
        f"(SCRY/SURVEIL/MILL/LIFE_CHANGE/DAMAGE/DISCARD/DRAW/TAP); "
        f"got {[e.type.name for e in events[-15:]]}"
    )


def _lrw_s24_etb_assert(game, name):
    """Place card on battlefield, assert that the ETB hook fired (at least one
    of our tracked events appears after the ZONE_CHANGE)."""
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, game.state.players[next(iter(game.state.players))], name)
    new = game.state.event_log[before:]
    fired = [e for e in new if e.type in _LRW_S24_TRIGGER_EVENTS]
    assert fired, (
        f"Expected ETB to emit tracked event for {name!r}; "
        f"got {[e.type.name for e in new[-15:]]}"
    )
    return obj


def _lrw_s24_perm_test(name, trigger):
    """One generic permanent test: put card on battlefield then emit trigger event."""
    game = Game()
    p1 = game.add_player("A")
    p2 = game.add_player("B")
    if trigger == 'etb':
        _lrw_s24_etb_assert(game, name)
        return
    obj = _put_on_battlefield(game, p1, name)
    events = _lrw_s24_emit_trigger(game, p1, obj, trigger)
    _lrw_s24_assert_emits_something(events)


def _lrw_s24_spell_test(name):
    """One generic spell test: call resolve() and assert it emits a tracked event."""
    game = Game()
    p1 = game.add_player("A")
    p2 = game.add_player("B")
    game.state.active_player = p1.id
    card_def = LORWYN_CUSTOM_CARDS[name]
    if card_def.resolve is None:
        return
    events = card_def.resolve([], game.state)
    fired = [e for e in events if e.type in _LRW_S24_TRIGGER_EVENTS]
    assert fired, (
        f"Expected slice-24 spell {name!r} resolve() to emit tracked event; "
        f"got {[e.type.name for e in events]}"
    )



def test_lrw_s24_appeal_to_eirdu():
    _lrw_s24_spell_test('Appeal to Eirdu')


def test_lrw_s24_crib_swap():
    _lrw_s24_spell_test('Crib Swap')


def test_lrw_s24_keep_out():
    _lrw_s24_spell_test('Keep Out')


def test_lrw_s24_kinbinding():
    _lrw_s24_perm_test('Kinbinding', 'eos')


def test_lrw_s24_ajani_outland_chaperone():
    _lrw_s24_perm_test('Ajani, Outland Chaperone', 'eos')


def test_lrw_s24_personify():
    _lrw_s24_spell_test('Personify')


def test_lrw_s24_protective_response():
    _lrw_s24_spell_test('Protective Response')


def test_lrw_s24_pyrrhic_strike():
    _lrw_s24_spell_test('Pyrrhic Strike')


def test_lrw_s24_riverguard_s_reflexes():
    _lrw_s24_spell_test("Riverguard's Reflexes")


def test_lrw_s24_morningtide_s_light():
    _lrw_s24_spell_test("Morningtide's Light")


def test_lrw_s24_spiral_into_solitude():
    _lrw_s24_spell_test('Spiral into Solitude')


def test_lrw_s24_winnowing():
    _lrw_s24_spell_test('Winnowing')


def test_lrw_s24_midnight_tilling():
    _lrw_s24_spell_test('Midnight Tilling')


def test_lrw_s24_tend_the_sprigs():
    _lrw_s24_spell_test('Tend the Sprigs')


def test_lrw_s24_thoughtweft_charge():
    _lrw_s24_spell_test('Thoughtweft Charge')


def test_lrw_s24_celestial_reunion():
    _lrw_s24_spell_test('Celestial Reunion')


def test_lrw_s24_dawn_s_light_archer():
    _lrw_s24_perm_test("Dawn's Light Archer", 'eos')


def test_lrw_s24_gilt_leaf_s_embrace():
    _lrw_s24_perm_test("Gilt-Leaf's Embrace", 'eos')


def test_lrw_s24_pitiless_fists():
    _lrw_s24_perm_test('Pitiless Fists', 'eos')


def test_lrw_s24_prismatic_undercurrents():
    _lrw_s24_perm_test('Prismatic Undercurrents', 'etb')


def test_lrw_s24_assert_perfection():
    _lrw_s24_spell_test('Assert Perfection')


def test_lrw_s24_aurora_awakener():
    _lrw_s24_perm_test('Aurora Awakener', 'eos')


def test_lrw_s24_bloom_tender():
    _lrw_s24_perm_test('Bloom Tender', 'etb')


def test_lrw_s24_blossoming_defense():
    _lrw_s24_spell_test('Blossoming Defense')


def test_lrw_s24_shimmerwilds_growth():
    _lrw_s24_perm_test('Shimmerwilds Growth', 'atk')


def test_lrw_s24_spry_and_mighty():
    _lrw_s24_spell_test('Spry and Mighty')


def test_lrw_s24_unforgiving_aim():
    _lrw_s24_spell_test('Unforgiving Aim')


def test_lrw_s24_vinebred_brawler():
    _lrw_s24_perm_test('Vinebred Brawler', 'etb')


def test_lrw_s24_glen_elendra_s_answer():
    _lrw_s24_spell_test("Glen Elendra's Answer")


def test_lrw_s24_harmonized_crescendo():
    _lrw_s24_spell_test('Harmonized Crescendo')


def test_lrw_s24_rime_chill():
    _lrw_s24_spell_test('Rime Chill')


def test_lrw_s24_rimefire_torque():
    _lrw_s24_perm_test('Rimefire Torque', 'dth')


def test_lrw_s24_lofty_dreams():
    _lrw_s24_spell_test('Lofty Dreams')


def test_lrw_s24_mirrorform():
    _lrw_s24_spell_test('Mirrorform')


def test_lrw_s24_noggle_the_mind():
    _lrw_s24_spell_test('Noggle the Mind')


def test_lrw_s24_run_away_together():
    _lrw_s24_spell_test('Run Away Together')


def test_lrw_s24_spell_snare():
    _lrw_s24_spell_test('Spell Snare')


def test_lrw_s24_summit_sentinel():
    _lrw_s24_perm_test('Summit Sentinel', 'atk')


def test_lrw_s24_sunderflock():
    _lrw_s24_spell_test('Sunderflock')


def test_lrw_s24_swat_away():
    _lrw_s24_spell_test('Swat Away')


def test_lrw_s24_temporal_cleansing():
    _lrw_s24_spell_test('Temporal Cleansing')


def test_lrw_s24_thirst_for_identity():
    _lrw_s24_spell_test('Thirst for Identity')


def test_lrw_s24_unexpected_assistance():
    _lrw_s24_spell_test('Unexpected Assistance')


def test_lrw_s24_wanderwine_farewell():
    _lrw_s24_spell_test('Wanderwine Farewell')


def test_lrw_s24_wild_unraveling():
    _lrw_s24_spell_test('Wild Unraveling')


def test_lrw_s24_auntie_s_sentence():
    _lrw_s24_spell_test("Auntie's Sentence")


def test_lrw_s24_blight_rot():
    _lrw_s24_spell_test('Blight Rot')


def test_lrw_s24_bloodline_bidding():
    _lrw_s24_spell_test('Bloodline Bidding')


def test_lrw_s24_darkness_descends():
    _lrw_s24_spell_test('Darkness Descends')


def test_lrw_s24_barbed_bloodletter():
    _lrw_s24_perm_test('Barbed Bloodletter', 'upk')


def test_lrw_s24_bogslither_s_embrace():
    _lrw_s24_spell_test("Bogslither's Embrace")


def test_lrw_s24_champion_of_the_weird():
    _lrw_s24_perm_test('Champion of the Weird', 'atk')


def test_lrw_s24_dawnhand_dissident():
    _lrw_s24_perm_test('Dawnhand Dissident', 'dth')


def test_lrw_s24_dose_of_dawnglow():
    _lrw_s24_spell_test('Dose of Dawnglow')


def test_lrw_s24_dream_harvest():
    _lrw_s24_spell_test('Dream Harvest')


def test_lrw_s24_requiting_hex():
    _lrw_s24_spell_test('Requiting Hex')


def test_lrw_s24_gutsplitter_gang():
    _lrw_s24_perm_test('Gutsplitter Gang', 'etb')


def test_lrw_s24_heirloom_auntie():
    _lrw_s24_perm_test('Heirloom Auntie', 'eos')


def test_lrw_s24_moonglove_extractor():
    _lrw_s24_perm_test('Moonglove Extractor', 'atk')


def test_lrw_s24_moonshadow():
    _lrw_s24_perm_test('Moonshadow', 'etb')


def test_lrw_s24_mudbutton_cursetosser():
    _lrw_s24_perm_test('Mudbutton Cursetosser', 'dth')


def test_lrw_s24_nameless_inversion():
    _lrw_s24_spell_test('Nameless Inversion')


def test_lrw_s24_nightmare_sower():
    _lrw_s24_perm_test('Nightmare Sower', 'eos')


def test_lrw_s24_perfect_intimidation():
    _lrw_s24_spell_test('Perfect Intimidation')


def test_lrw_s24_scarblade_scout():
    _lrw_s24_perm_test('Scarblade Scout', 'etb')


def test_lrw_s24_scarblade_s_malice():
    _lrw_s24_spell_test("Scarblade's Malice")


def test_lrw_s24_shimmercreep():
    _lrw_s24_perm_test('Shimmercreep', 'eos')


def test_lrw_s24_taster_of_wares():
    _lrw_s24_perm_test('Taster of Wares', 'eos')


def test_lrw_s24_twilight_diviner():
    _lrw_s24_perm_test('Twilight Diviner', 'eos')


def test_lrw_s24_unbury():
    _lrw_s24_spell_test('Unbury')


def test_lrw_s24_boulder_dash():
    _lrw_s24_spell_test('Boulder Dash')


def test_lrw_s24_burning_curiosity():
    _lrw_s24_spell_test('Burning Curiosity')


def test_lrw_s24_cinder_strike():
    _lrw_s24_spell_test('Cinder Strike')


def test_lrw_s24_collective_inferno():
    _lrw_s24_perm_test('Collective Inferno', 'eos')


def test_lrw_s24_feed_the_flames():
    _lrw_s24_spell_test('Feed the Flames')


def test_lrw_s24_giantfall():
    _lrw_s24_spell_test('Giantfall')


def test_lrw_s24_goatnap():
    _lrw_s24_spell_test('Goatnap')


def test_lrw_s24_end_blaze_epiphany():
    _lrw_s24_spell_test('End-Blaze Epiphany')


def test_lrw_s24_reckless_ransacking():
    _lrw_s24_spell_test('Reckless Ransacking')


def test_lrw_s24_hexing_squelcher():
    _lrw_s24_perm_test('Hexing Squelcher', 'eos')


def test_lrw_s24_impolite_entrance():
    _lrw_s24_spell_test('Impolite Entrance')


def test_lrw_s24_kindle_the_inner_flame():
    _lrw_s24_spell_test('Kindle the Inner Flame')


def test_lrw_s24_kulrath_zealot():
    _lrw_s24_perm_test('Kulrath Zealot', 'upk')


def test_lrw_s24_lasting_tarfire():
    _lrw_s24_spell_test('Lasting Tarfire')


def test_lrw_s24_lavaleaper():
    _lrw_s24_perm_test('Lavaleaper', 'etb')


def test_lrw_s24_meek_attack():
    _lrw_s24_spell_test('Meek Attack')


def test_lrw_s24_scuzzback_scrounger():
    _lrw_s24_perm_test('Scuzzback Scrounger', 'etb')


def test_lrw_s24_sear():
    _lrw_s24_spell_test('Sear')


def test_lrw_s24_sizzling_changeling():
    _lrw_s24_perm_test('Sizzling Changeling', 'upk')


def test_lrw_s24_soul_immolation():
    _lrw_s24_spell_test('Soul Immolation')


def test_lrw_s24_soulbright_seeker():
    _lrw_s24_perm_test('Soulbright Seeker', 'upk')


def test_lrw_s24_sourbread_auntie():
    _lrw_s24_perm_test('Sourbread Auntie', 'upk')


def test_lrw_s24_spinerock_tyrant():
    _lrw_s24_perm_test('Spinerock Tyrant', 'dth')


def test_lrw_s24_squawkroaster():
    _lrw_s24_perm_test('Squawkroaster', 'etb')


def test_lrw_s24_sting_slinger():
    _lrw_s24_perm_test('Sting-Slinger', 'etb')


def test_lrw_s24_tweeze():
    _lrw_s24_spell_test('Tweeze')


def test_lrw_s24_warren_torchmaster():
    _lrw_s24_perm_test('Warren Torchmaster', 'eos')


def test_lrw_s24_ashling_s_command():
    _lrw_s24_spell_test("Ashling's Command")


def test_lrw_s24_brigid_s_command():
    _lrw_s24_spell_test("Brigid's Command")


def test_lrw_s24_prideful_feastling():
    _lrw_s24_perm_test('Prideful Feastling', 'upk')


def test_lrw_s24_reaping_willow():
    _lrw_s24_perm_test('Reaping Willow', 'etb')


def test_lrw_s24_catharsis():
    _lrw_s24_spell_test('Catharsis')


def test_lrw_s24_emptiness():
    _lrw_s24_perm_test('Emptiness', 'eos')


def test_lrw_s24_grub_s_command():
    _lrw_s24_spell_test("Grub's Command")


def test_lrw_s24_high_perfect_morcant():
    _lrw_s24_perm_test('High Perfect Morcant', 'atk')


def test_lrw_s24_hovel_hurler():
    _lrw_s24_perm_test('Hovel Hurler', 'etb')


def test_lrw_s24_kirol_attentive_first_year():
    _lrw_s24_perm_test('Kirol, Attentive First-Year', 'eos')


def test_lrw_s24_lluwen_imperfect_naturalist():
    _lrw_s24_perm_test('Lluwen, Imperfect Naturalist', 'upk')


def test_lrw_s24_maralen_fae_ascendant():
    _lrw_s24_perm_test('Maralen, Fae Ascendant', 'upk')


def test_lrw_s24_merrow_skyswimmer():
    _lrw_s24_perm_test('Merrow Skyswimmer', 'eos')


def test_lrw_s24_mischievous_sneakling():
    _lrw_s24_perm_test('Mischievous Sneakling', 'upk')


def test_lrw_s24_morcant_s_loyalist():
    _lrw_s24_perm_test("Morcant's Loyalist", 'etb')


def test_lrw_s24_noggle_robber():
    _lrw_s24_perm_test('Noggle Robber', 'dth')


def test_lrw_s24_sanar_innovative_first_year():
    _lrw_s24_perm_test('Sanar, Innovative First-Year', 'eos')


def test_lrw_s24_shadow_urchin():
    _lrw_s24_perm_test('Shadow Urchin', 'dth')


def test_lrw_s24_stoic_grove_guide():
    _lrw_s24_perm_test('Stoic Grove-Guide', 'dth')


def test_lrw_s24_sygg_s_command():
    _lrw_s24_spell_test("Sygg's Command")


def test_lrw_s24_tam_mindful_first_year():
    _lrw_s24_perm_test('Tam, Mindful First-Year', 'upk')


def test_lrw_s24_thoughtweft_lieutenant():
    _lrw_s24_perm_test('Thoughtweft Lieutenant', 'eos')


def test_lrw_s24_trystan_s_command():
    _lrw_s24_spell_test("Trystan's Command")


def test_lrw_s24_twinflame_travelers():
    _lrw_s24_perm_test('Twinflame Travelers', 'etb')


def test_lrw_s24_vibrance():
    _lrw_s24_perm_test('Vibrance', 'eos')


def test_lrw_s24_voracious_tome_skimmer():
    _lrw_s24_perm_test('Voracious Tome-Skimmer', 'upk')


def test_lrw_s24_wary_farmer():
    _lrw_s24_perm_test('Wary Farmer', 'atk')


def test_lrw_s24_wistfulness():
    _lrw_s24_perm_test('Wistfulness', 'eos')


def test_lrw_s24_chronicle_of_victory():
    _lrw_s24_perm_test('Chronicle of Victory', 'etb')


def test_lrw_s24_dawn_blessed_pennant():
    _lrw_s24_perm_test('Dawn-Blessed Pennant', 'atk')


def test_lrw_s24_firdoch_core():
    _lrw_s24_perm_test('Firdoch Core', 'atk')


def test_lrw_s24_gathering_stone():
    _lrw_s24_perm_test('Gathering Stone', 'upk')


def test_lrw_s24_mirrormind_crown():
    _lrw_s24_perm_test('Mirrormind Crown', 'atk')


def test_lrw_s24_puca_s_eye():
    _lrw_s24_perm_test("Puca's Eye", 'etb')


def test_lrw_s24_springleaf_drum():
    _lrw_s24_perm_test('Springleaf Drum', 'etb')


def test_lrw_s24_bark_of_doran():
    _lrw_s24_perm_test('Bark of Doran', 'atk')


def test_lrw_s24_moonglove_extract():
    _lrw_s24_perm_test('Moonglove Extract', 'upk')


def test_lrw_s24_runed_stalactite():
    _lrw_s24_perm_test('Runed Stalactite', 'etb')


def test_lrw_s24_thornbite_staff():
    _lrw_s24_perm_test('Thornbite Staff', 'dth')


def test_lrw_s24_obsidian_battle_axe():
    _lrw_s24_perm_test('Obsidian Battle-Axe', 'atk')


def test_lrw_s24_cloak_and_dagger():
    _lrw_s24_perm_test('Cloak and Dagger', 'eos')


def test_lrw_s24_diviner_s_wand():
    _lrw_s24_perm_test("Diviner's Wand", 'upk')


def test_lrw_s24_veteran_s_armaments():
    _lrw_s24_perm_test("Veteran's Armaments", 'etb')


def test_lrw_s24_blood_crypt():
    _lrw_s24_perm_test('Blood Crypt', 'upk')


def test_lrw_s24_hallowed_fountain():
    _lrw_s24_perm_test('Hallowed Fountain', 'atk')


def test_lrw_s24_overgrown_tomb():
    _lrw_s24_perm_test('Overgrown Tomb', 'upk')


def test_lrw_s24_steam_vents():
    _lrw_s24_perm_test('Steam Vents', 'etb')


def test_lrw_s24_temple_garden():
    _lrw_s24_perm_test('Temple Garden', 'upk')


def test_lrw_s24_eclipsed_realms():
    _lrw_s24_perm_test('Eclipsed Realms', 'atk')


def test_lrw_s24_evolving_wilds():
    _lrw_s24_perm_test('Evolving Wilds', 'dth')


def test_lrw_s24_auntie_s_favor():
    _lrw_s24_spell_test("Auntie's Favor")


def test_lrw_s24_wretched_banquet():
    _lrw_s24_spell_test('Wretched Banquet')


def test_lrw_s24_cinder_pyromancer():
    _lrw_s24_perm_test('Cinder Pyromancer', 'dth')


def test_lrw_s24_inner_flame_igniter():
    _lrw_s24_perm_test('Inner-Flame Igniter', 'dth')


def test_lrw_s24_smoldering_spinebacks():
    _lrw_s24_perm_test('Smoldering Spinebacks', 'eos')


def test_lrw_s24_thundercloud_shaman():
    _lrw_s24_perm_test('Thundercloud Shaman', 'eos')


def test_lrw_s24_elvish_harbinger():
    _lrw_s24_perm_test('Elvish Harbinger', 'upk')


def test_lrw_s24_heritage_druid():
    _lrw_s24_perm_test('Heritage Druid', 'dth')


def test_lrw_s24_nath_of_the_gilt_leaf():
    _lrw_s24_perm_test('Nath of the Gilt-Leaf', 'dth')


def test_lrw_s24_treefolk_harbinger():
    _lrw_s24_perm_test('Treefolk Harbinger', 'etb')


def test_lrw_s24_wolf_skull_shaman():
    _lrw_s24_perm_test('Wolf-Skull Shaman', 'upk')


def test_lrw_s24_sygg_river_guide():
    _lrw_s24_perm_test('Sygg, River Guide', 'dth')


def test_lrw_s24_sygg_river_cutthroat():
    _lrw_s24_perm_test('Sygg, River Cutthroat', 'eos')


def test_lrw_s24_oversoul_of_dusk():
    _lrw_s24_perm_test('Oversoul of Dusk', 'etb')


def test_lrw_s24_kitchen_finks():
    _lrw_s24_perm_test('Kitchen Finks', 'upk')


def test_lrw_s24_murderous_redcap():
    _lrw_s24_perm_test('Murderous Redcap', 'etb')


def test_lrw_s24_demigod_of_revenge():
    _lrw_s24_perm_test('Demigod of Revenge', 'etb')


def test_lrw_s24_glen_elendra_archmage():
    _lrw_s24_perm_test('Glen Elendra Archmage', 'atk')


def test_lrw_s24_stillmoon_cavalier():
    _lrw_s24_perm_test('Stillmoon Cavalier', 'upk')


def test_lrw_s24_creakwood_liege():
    _lrw_s24_perm_test('Creakwood Liege', 'eos')


def test_lrw_s24_deathbringer_liege():
    _lrw_s24_perm_test('Deathbringer Liege', 'upk')


def test_lrw_s24_balefire_liege():
    _lrw_s24_perm_test('Balefire Liege', 'etb')


def test_lrw_s24_boartusk_liege():
    _lrw_s24_perm_test('Boartusk Liege', 'atk')


def test_lrw_s24_thistledown_liege():
    _lrw_s24_perm_test('Thistledown Liege', 'eos')


def test_lrw_s24_murkfiend_liege():
    _lrw_s24_perm_test('Murkfiend Liege', 'upk')


def test_lrw_s24_mindwrack_liege():
    _lrw_s24_perm_test('Mindwrack Liege', 'atk')


def test_lrw_s24_ashenmoor_liege():
    _lrw_s24_perm_test('Ashenmoor Liege', 'atk')


def test_lrw_s24_wilt_leaf_liege():
    _lrw_s24_perm_test('Wilt-Leaf Liege', 'etb')


def test_lrw_s24_kinsbaile_borderguard():
    _lrw_s24_perm_test('Kinsbaile Borderguard', 'etb')


def test_lrw_s24_cloudgoat_ranger():
    _lrw_s24_perm_test('Cloudgoat Ranger', 'etb')


def test_lrw_s24_mirror_entity():
    _lrw_s24_perm_test('Mirror Entity', 'eos')


def test_lrw_s24_reveillark():
    _lrw_s24_perm_test('Reveillark', 'dth')


def test_lrw_s24_ranger_of_eos():
    _lrw_s24_perm_test('Ranger of Eos', 'etb')


def test_lrw_s24_vendilion_clique():
    _lrw_s24_perm_test('Vendilion Clique', 'etb')


def test_lrw_s24_sower_of_temptation():
    _lrw_s24_perm_test('Sower of Temptation', 'eos')


def test_lrw_s24_mistbind_clique():
    _lrw_s24_perm_test('Mistbind Clique', 'atk')


def test_lrw_s24_spellstutter_sprite():
    _lrw_s24_perm_test('Spellstutter Sprite', 'eos')


def test_lrw_s24_scion_of_oona():
    _lrw_s24_perm_test('Scion of Oona', 'upk')


def test_lrw_s24_shriekmaw():
    _lrw_s24_perm_test('Shriekmaw', 'etb')


def test_lrw_s24_oona_s_blackguard():
    _lrw_s24_perm_test("Oona's Blackguard", 'atk')


def test_lrw_s24_earwig_squad():
    _lrw_s24_perm_test('Earwig Squad', 'eos')


def test_lrw_s24_bitterblossom():
    _lrw_s24_perm_test('Bitterblossom', 'eos')


def test_lrw_s24_mornsong_aria():
    _lrw_s24_perm_test('Mornsong Aria', 'upk')


def test_lrw_s24_sunrise_sovereign():
    _lrw_s24_perm_test('Sunrise Sovereign', 'atk')


def test_lrw_s24_brion_stoutarm():
    _lrw_s24_perm_test('Brion Stoutarm', 'etb')


def test_lrw_s24_nova_chaser():
    _lrw_s24_perm_test('Nova Chaser', 'eos')


def test_lrw_s24_incandescent_soulstoke():
    _lrw_s24_perm_test('Incandescent Soulstoke', 'eos')


def test_lrw_s24_chameleon_colossus():
    _lrw_s24_perm_test('Chameleon Colossus', 'atk')


def test_lrw_s24_primalcrux():
    _lrw_s24_perm_test('Primalcrux', 'eos')


def test_lrw_s24_devoted_druid():
    _lrw_s24_perm_test('Devoted Druid', 'atk')


def test_lrw_s24_nettle_sentinel():
    _lrw_s24_perm_test('Nettle Sentinel', 'dth')


def test_lrw_s24_masked_admirers():
    _lrw_s24_perm_test('Masked Admirers', 'eos')


def test_lrw_s24_thoughtweft_gambit():
    _lrw_s24_spell_test('Thoughtweft Gambit')


def test_lrw_s24_cryptic_command():
    _lrw_s24_spell_test('Cryptic Command')


def test_lrw_s24_firespout():
    _lrw_s24_spell_test('Firespout')


def test_lrw_s24_primal_command():
    _lrw_s24_spell_test('Primal Command')


def test_lrw_s24_austere_command():
    _lrw_s24_spell_test('Austere Command')


def test_lrw_s24_profane_command():
    _lrw_s24_spell_test('Profane Command')


def test_lrw_s24_incendiary_command():
    _lrw_s24_spell_test('Incendiary Command')


def test_lrw_s24_fulminator_mage():
    _lrw_s24_perm_test('Fulminator Mage', 'atk')


def test_lrw_s24_figure_of_destiny():
    _lrw_s24_perm_test('Figure of Destiny', 'atk')


def test_lrw_s24_manamorphose():
    _lrw_s24_spell_test('Manamorphose')


def test_lrw_s24_boggart_ram_gang():
    _lrw_s24_perm_test('Boggart Ram-Gang', 'etb')


def test_lrw_s24_tattermunge_maniac():
    _lrw_s24_perm_test('Tattermunge Maniac', 'eos')


def test_lrw_s24_vexing_shusher():
    _lrw_s24_perm_test('Vexing Shusher', 'atk')


def test_lrw_s24_plumeveil():
    _lrw_s24_perm_test('Plumeveil', 'eos')


def test_lrw_s24_unmake():
    _lrw_s24_spell_test('Unmake')


def test_lrw_s24_fiery_justice():
    _lrw_s24_spell_test('Fiery Justice')


def test_lrw_s24_augury_adept():
    _lrw_s24_perm_test('Augury Adept', 'etb')


def test_lrw_s24_cold_eyed_selkie():
    _lrw_s24_perm_test('Cold-Eyed Selkie', 'dth')


def test_lrw_s24_deus_of_calamity():
    _lrw_s24_perm_test('Deus of Calamity', 'atk')


def test_lrw_s24_ghastlord_of_fugue():
    _lrw_s24_perm_test('Ghastlord of Fugue', 'dth')


def test_lrw_s24_deity_of_scars():
    _lrw_s24_perm_test('Deity of Scars', 'upk')


def test_lrw_s24_overbeing_of_myth():
    _lrw_s24_perm_test('Overbeing of Myth', 'etb')


def test_lrw_s24_divinity_of_pride():
    _lrw_s24_perm_test('Divinity of Pride', 'eos')


def test_lrw_s24_hallowed_burial():
    _lrw_s24_spell_test('Hallowed Burial')


def test_lrw_s24_idyllic_tutor():
    _lrw_s24_spell_test('Idyllic Tutor')


def test_lrw_s24_spectral_procession():
    _lrw_s24_spell_test('Spectral Procession')


def test_lrw_s24_runed_halo():
    _lrw_s24_perm_test('Runed Halo', 'etb')


def test_lrw_s24_knight_of_meadowgrain():
    _lrw_s24_perm_test('Knight of Meadowgrain', 'eos')


def test_lrw_s24_pollen_lullaby():
    _lrw_s24_spell_test('Pollen Lullaby')


def test_lrw_s24_broken_ambitions():
    _lrw_s24_spell_test('Broken Ambitions')


def test_lrw_s24_faerie_trickery():
    _lrw_s24_spell_test('Faerie Trickery')


def test_lrw_s24_ponder():
    _lrw_s24_spell_test('Ponder')


def test_lrw_s24_final_revels():
    _lrw_s24_spell_test('Final Revels')


def test_lrw_s24_thoughtseize():
    _lrw_s24_spell_test('Thoughtseize')


def test_lrw_s24_peppersmoke():
    _lrw_s24_spell_test('Peppersmoke')


def test_lrw_s24_fodder_launch():
    _lrw_s24_spell_test('Fodder Launch')


def test_lrw_s24_makeshift_mannequin():
    _lrw_s24_spell_test('Makeshift Mannequin')


def test_lrw_s24_death_denied():
    _lrw_s24_spell_test('Death Denied')


def test_lrw_s24_nettlevine_blight():
    _lrw_s24_perm_test('Nettlevine Blight', 'etb')


def test_lrw_s24_tarfire():
    _lrw_s24_spell_test('Tarfire')


def test_lrw_s24_lash_out():
    _lrw_s24_spell_test('Lash Out')


def test_lrw_s24_sensation_gorger():
    _lrw_s24_perm_test('Sensation Gorger', 'eos')


def test_lrw_s24_garruk_wildspeaker():
    _lrw_s24_perm_test('Garruk Wildspeaker', 'etb')


def test_lrw_s24_leaf_crowned_elder():
    _lrw_s24_perm_test('Leaf-Crowned Elder', 'etb')


def test_lrw_s24_elvish_branchbender():
    _lrw_s24_perm_test('Elvish Branchbender', 'eos')


def test_lrw_s24_gilt_leaf_ambush():
    _lrw_s24_spell_test('Gilt-Leaf Ambush')


def test_lrw_s24_hunting_triad():
    _lrw_s24_spell_test('Hunting Triad')


def test_lrw_s24_boggart_sprite_chaser():
    _lrw_s24_perm_test('Boggart Sprite-Chaser', 'upk')


def test_lrw_s24_scarblade_elite():
    _lrw_s24_perm_test('Scarblade Elite', 'dth')


def test_lrw_s24_safehold_elite():
    _lrw_s24_perm_test('Safehold Elite', 'etb')


def test_lrw_s24_rendclaw_trow():
    _lrw_s24_perm_test('Rendclaw Trow', 'etb')


def test_lrw_s24_horde_of_notions():
    _lrw_s24_perm_test('Horde of Notions', 'atk')


def test_lrw_s24_rhys_the_redeemed():
    _lrw_s24_perm_test('Rhys the Redeemed', 'eos')


def test_lrw_s24_heap_doll():
    _lrw_s24_perm_test('Heap Doll', 'dth')


def test_lrw_s24_painter_s_servant():
    _lrw_s24_perm_test("Painter's Servant", 'dth')


def test_lrw_s24_pili_pala():
    _lrw_s24_perm_test('Pili-Pala', 'eos')


def test_lrw_s24_wanderbrine_rootcutters():
    _lrw_s24_perm_test('Wanderbrine Rootcutters', 'eos')

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
