"""
Avatar: The Last Airbender (Custom) Spice Pass Tests (Phase A1)

Validates the format-defining cards added in the Phase A1 spice pass
on `src/cards/custom/penultimate_avatar.py`.

Cards covered:
- Sokka's Boomerang (REWIRE — was unwired legendary equipment)
- Aang's Staff (REWIRE — was unwired legendary equipment)
- Toph's Bracelet (REWIRE — was unwired legendary equipment)
- Iroh, Dragon of the West (REWIRE — upkeep now deals 1 to each opp)
- Fire Lord Ozai, Phoenix King (NEW — Mountain-gated indestructible mythic)
- The Four Nations Restored (NEW — multi-color anthem build-around)
- Siege of Ba Sing Se (NEW — 3-chapter saga)
"""

import os
import sys
# Worktree-portable sys.path: compute repo root from this file's location so
# the test runs from any checkout (main or a `.claude/worktrees/agent-*/`).
# Hardcoding the main-checkout path causes silent stale loads — see
# spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.penultimate_avatar import AVATAR_TLA_CUSTOM_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the ZLD spice-test harness shape.

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE to
    battlefield, runs setup exactly once via the pipeline (the correct
    path)."""
    card_def = AVATAR_TLA_CUSTOM_CARDS[card_name]
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
# Sokka's Boomerang (REWIRE)
# ============================================================================

def test_sokkas_boomerang_loads():
    """Equipment setup registers PT-mod + equip-cost ability."""
    print("\n=== Sokka's Boomerang: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    boom = _put_on_battlefield(game, p1, "Sokka's Boomerang")
    assert boom.zone == ZoneType.BATTLEFIELD
    activated = getattr(boom.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Sokka's Boomerang"
    # PT-mod interceptors live on the equipment.
    assert len(boom.interceptor_ids) >= 1, (
        f"Expected PT interceptors; got {len(boom.interceptor_ids)}"
    )


def test_sokkas_boomerang_pt_mod_on_attach():
    """After ATTACH, equipped creature reads +1/+1 via PT query aggregation."""
    print("\n=== Sokka's Boomerang: +1/+1 on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    boom = _put_on_battlefield(game, p1, "Sokka's Boomerang")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")
    base_p = get_power(sokka, game.state)
    base_t = get_toughness(sokka, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': boom.id, 'target_id': sokka.id},
        source=boom.id,
    ))

    new_p = get_power(sokka, game.state)
    new_t = get_toughness(sokka, game.state)
    assert new_p == base_p + 1, f"Expected power +1: {base_p}->{new_p}"
    assert new_t == base_t + 1, f"Expected toughness +1: {base_t}->{new_t}"


def test_sokkas_boomerang_unattached_no_buff():
    """Edge: PT mod must NOT apply to creatures the boomerang is not attached to."""
    print("\n=== Sokka's Boomerang: unattached -> no buff ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Sokka's Boomerang")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")
    base_p = get_power(sokka, game.state)
    # No ATTACH event has fired.
    new_p = get_power(sokka, game.state)
    assert new_p == base_p, f"Expected no buff without ATTACH; got {base_p}->{new_p}"


# ============================================================================
# Aang's Staff (REWIRE)
# ============================================================================

def test_aangs_staff_loads():
    print("\n=== Aang's Staff: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    staff = _put_on_battlefield(game, p1, "Aang's Staff")
    assert staff.zone == ZoneType.BATTLEFIELD
    activated = getattr(staff.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Aang's Staff"


def test_aangs_staff_grants_flying_on_attach():
    """ATTACH gives +2/+0 + flying."""
    print("\n=== Aang's Staff: +2/+0 + flying ===")
    game = Game()
    p1 = game.add_player("Alice")
    staff = _put_on_battlefield(game, p1, "Aang's Staff")
    # Equip a non-flying creature.
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")
    base_p = get_power(sokka, game.state)
    assert not has_ability(sokka, "flying", game.state), (
        "Sokka should not have flying pre-attach"
    )

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': staff.id, 'target_id': sokka.id},
        source=staff.id,
    ))

    new_p = get_power(sokka, game.state)
    assert new_p == base_p + 2, f"Expected +2 power: {base_p}->{new_p}"
    assert has_ability(sokka, "flying", game.state), (
        "Expected flying after Aang's Staff attach"
    )


# ============================================================================
# Toph's Bracelet (REWIRE)
# ============================================================================

def test_tophs_bracelet_loads():
    print("\n=== Toph's Bracelet: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    brc = _put_on_battlefield(game, p1, "Toph's Bracelet")
    assert brc.zone == ZoneType.BATTLEFIELD
    activated = getattr(brc.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Toph's Bracelet"


def test_tophs_bracelet_grants_trample_on_attach():
    """ATTACH gives +1/+2 + trample."""
    print("\n=== Toph's Bracelet: +1/+2 + trample ===")
    game = Game()
    p1 = game.add_player("Alice")
    brc = _put_on_battlefield(game, p1, "Toph's Bracelet")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")
    base_p = get_power(sokka, game.state)
    base_t = get_toughness(sokka, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': brc.id, 'target_id': sokka.id},
        source=brc.id,
    ))

    new_p = get_power(sokka, game.state)
    new_t = get_toughness(sokka, game.state)
    assert new_p == base_p + 1
    assert new_t == base_t + 2
    assert has_ability(sokka, "trample", game.state)


# ============================================================================
# Iroh, Dragon of the West (REWIRE upkeep)
# ============================================================================

def test_iroh_upkeep_emits_damage_to_each_opponent():
    """Own upkeep deals 1 damage to each opponent."""
    print("\n=== Iroh: upkeep ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    iroh = _put_on_battlefield(game, p1, "Iroh, Dragon of the West")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    damages = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 1
        and e.payload.get('source') == iroh.id
    ]
    assert damages, (
        f"Expected DAMAGE 1 to opp on upkeep; recent={[e.type.name for e in new[-10:]]}"
    )


def test_iroh_upkeep_opp_does_not_fire():
    """Opp upkeep does not trigger Iroh's ping."""
    print("\n=== Iroh: opp upkeep -> no fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    iroh = _put_on_battlefield(game, p1, "Iroh, Dragon of the West")

    before = len(game.state.event_log)
    game.state.active_player = p2.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    damages = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('source') == iroh.id
    ]
    assert not damages, "Iroh fired during opp upkeep"


# ============================================================================
# Fire Lord Ozai, Phoenix King
# ============================================================================

def test_ozai_phoenix_king_loads():
    print("\n=== Fire Lord Ozai, Phoenix King: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ozai = _put_on_battlefield(game, p1, "Fire Lord Ozai, Phoenix King")
    assert ozai.zone == ZoneType.BATTLEFIELD
    # menace always; indestructible gated; attack trigger.
    assert len(ozai.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors; got {len(ozai.interceptor_ids)}"
    )
    assert has_ability(ozai, "menace", game.state)


def test_ozai_indestructible_gated_on_mountains():
    """Without 5+ Mountains, NOT indestructible. With 5: indestructible."""
    print("\n=== Ozai: indestructible only with 5+ Mountains ===")
    game = Game()
    p1 = game.add_player("Alice")
    ozai = _put_on_battlefield(game, p1, "Fire Lord Ozai, Phoenix King")
    # Zero mountains -> not indestructible.
    assert not has_ability(ozai, "indestructible", game.state)
    # Add 5 Mountains.
    for _ in range(5):
        _put_on_battlefield(game, p1, "Mountain")
    assert has_ability(ozai, "indestructible", game.state), (
        "Expected indestructible with 5 Mountains"
    )


def test_ozai_attack_pings_each_opponent():
    """Attack trigger emits DAMAGE 2 to each opponent."""
    print("\n=== Ozai: attack ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ozai = _put_on_battlefield(game, p1, "Fire Lord Ozai, Phoenix King")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': ozai.id, 'attacker': ozai.id, 'controller': p1.id},
        source=ozai.id,
    ))
    new = game.state.event_log[before:]
    damages = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 2
        and e.payload.get('source') == ozai.id
    ]
    assert damages, (
        f"Expected DAMAGE 2 to p2 on attack; recent={[e.type.name for e in new[-10:]]}"
    )


# ============================================================================
# The Four Nations Restored
# ============================================================================

def test_four_nations_restored_loads():
    print("\n=== The Four Nations Restored: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    fn = _put_on_battlefield(game, p1, "The Four Nations Restored")
    assert fn.zone == ZoneType.BATTLEFIELD
    assert fn.interceptor_ids, "Expected dynamic PT interceptors"


def test_four_nations_pumps_by_distinct_color_count():
    """+N/+N per distinct color among your creatures.

    Sokka, Swordsman is mono-white. With Sokka + Four Nations Restored on
    p1's board, distinct color count is 1, so Sokka reads +1/+1 over base.
    Adding a blue creature should jump to +2/+2.
    """
    print("\n=== Four Nations: dynamic color anthem ===")
    game = Game()
    p1 = game.add_player("Alice")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")  # mono-white
    base_p = sokka.characteristics.power
    base_t = sokka.characteristics.toughness
    _put_on_battlefield(game, p1, "The Four Nations Restored")

    # Distinct colors = {WHITE} -> N=1
    p1_after = get_power(sokka, game.state)
    t1_after = get_toughness(sokka, game.state)
    assert p1_after == base_p + 1, f"Expected +1 with 1 color: {base_p}->{p1_after}"
    assert t1_after == base_t + 1

    # Add a blue creature -> distinct colors = {WHITE, BLUE} -> N=2
    _put_on_battlefield(game, p1, "Knowledge Seeker")
    p2_after = get_power(sokka, game.state)
    t2_after = get_toughness(sokka, game.state)
    assert p2_after == base_p + 2, f"Expected +2 with 2 colors: {base_p}->{p2_after}"
    assert t2_after == base_t + 2


def test_four_nations_does_not_buff_opp_creatures():
    """Edge: only YOUR creatures get the buff."""
    print("\n=== Four Nations: opp creatures unaffected ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Sokka, Swordsman")
    _put_on_battlefield(game, p1, "The Four Nations Restored")
    opp_sokka = _put_on_battlefield(game, p2, "Sokka, Swordsman")
    base = opp_sokka.characteristics.power
    after = get_power(opp_sokka, game.state)
    assert after == base, f"Opp creature should be unbuffed: {base}->{after}"


# ============================================================================
# Siege of Ba Sing Se (saga)
# ============================================================================

def test_siege_of_ba_sing_se_loads():
    print("\n=== Siege of Ba Sing Se: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Siege of Ba Sing Se")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert saga.interceptor_ids, "Expected saga chapter interceptors"


def test_siege_of_ba_sing_se_chapter_i_emits_ally_tutor():
    """Direct chapter-I dispatch emits SEARCH_LIBRARY for Ally creature."""
    print("\n=== Siege of Ba Sing Se: chapter I ===")
    from src.cards.custom.penultimate_avatar import _siege_of_ba_sing_se_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Siege of Ba Sing Se")
    events = _siege_of_ba_sing_se_chapter_i(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert payload.get('subtypes_any') == ['Ally']
    assert payload.get('mana_value_max') == 3
    assert payload.get('enters_tapped') is True
    assert payload.get('destination') == 'battlefield'


def test_siege_of_ba_sing_se_chapter_ii_creates_two_earthbender_tokens():
    print("\n=== Siege of Ba Sing Se: chapter II ===")
    from src.cards.custom.penultimate_avatar import _siege_of_ba_sing_se_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Siege of Ba Sing Se")
    events = _siege_of_ba_sing_se_chapter_ii(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and e.payload.get('token', {}).get('subtypes', set()) & {'Soldier'}
    ]
    assert len(tokens) == 2


def test_siege_of_ba_sing_se_chapter_iii_anthem_excludes_saga():
    print("\n=== Siege of Ba Sing Se: chapter III ===")
    from src.cards.custom.penultimate_avatar import _siege_of_ba_sing_se_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Siege of Ba Sing Se")
    sokka = _put_on_battlefield(game, p1, "Sokka, Swordsman")
    events = _siege_of_ba_sing_se_chapter_iii(saga, game.state)
    targets = [
        e.payload['object_id']
        for e in events
        if e.type == EventType.PT_MODIFICATION
    ]
    assert sokka.id in targets, f"Sokka not buffed: {targets}"
    assert saga.id not in targets, f"Saga should not buff itself: {targets}"
    # +2/+1.
    matching = [
        e for e in events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == sokka.id
    ]
    assert matching
    assert matching[-1].payload.get('power_mod') == 2
    assert matching[-1].payload.get('toughness_mod') == 1


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
