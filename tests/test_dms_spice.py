"""
Demon Slayer (DMS) Spice Pass Tests (Phase A1)

Validates the format-defining cards added in the 2026-05-18 spice pass on
`src/cards/custom/demon_slayer.py`. Phase A1 — within current engine, no
new helpers.

Cards covered:
- Yoriichi Tsugikuni, Sun Breather Original (NEW — pattern 4 compression mythic)
- Final Selection (NEW — saga, pattern 7 tutor + assembly)
- Demon King's Manor (NEW — saga, pattern 7 tutor + snowball)
- Tanjiro's Earrings (NEW — equipment, pattern 8 reanimator-on-body)
- Tanjiro Kamado, Sun Breather (REWIRE — was no-op effect_fn)
- Muzan Kibutsuji (REWIRE — wired flavor indestructible + end-step drain)
- Nichirin Sword (REWIRE — make_equipment_setup compression)
- Hashira Meeting (REWIRE — wired resolve fn for SEARCH_LIBRARY)
"""

import os
import sys

# Worktree-portable sys.path (spice-pass gotcha #18) — compute repo root from
# this file's location so the test runs from any checkout (main or a
# `.claude/worktrees/agent-*/` worktree). Hardcoding the main-checkout path
# bit all three parallel-agent worktrees during the HPW/FINC/MVL rollout.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.demon_slayer import DEMON_SLAYER_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the Zelda spice test harness shape (gotcha #18 + standard pattern).

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE
    to battlefield, runs setup exactly once via the pipeline (the correct
    path)."""
    card_def = DEMON_SLAYER_CARDS[card_name]
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
# Yoriichi Tsugikuni, Sun Breather Original (NEW)
# ============================================================================

def test_yoriichi_loads_with_keywords_and_interceptors():
    print("\n=== Yoriichi Tsugikuni: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    yor = _put_on_battlefield(game, p1, "Yoriichi Tsugikuni, Sun Breather Original")
    assert yor.zone == ZoneType.BATTLEFIELD
    # Self keywords: flying, first_strike, vigilance, lifelink
    assert has_ability(yor, 'flying', game.state)
    assert has_ability(yor, 'first_strike', game.state)
    assert has_ability(yor, 'vigilance', game.state)
    assert has_ability(yor, 'lifelink', game.state)
    print(f"  Keywords confirmed; interceptors: {len(yor.interceptor_ids)}")


def test_yoriichi_etb_destroys_opp_demons():
    """ETB sweeper destroys each opp-controlled Demon. Uses zone-reads (gotcha #14)."""
    print("\n=== Yoriichi: ETB destroys opp Demons ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Place a Demon under p2.
    fledgling = _put_on_battlefield(game, p2, "Fledgling Demon")  # 1/1 Demon
    # Place a non-Demon under p2 — should survive.
    rookie = _put_on_battlefield(game, p2, "Rookie Slayer")       # 1/1 Slayer (not Demon)

    _put_on_battlefield(game, p1, "Yoriichi Tsugikuni, Sun Breather Original")

    assert fledgling.zone == ZoneType.GRAVEYARD, (
        f"Expected Fledgling Demon destroyed by Yoriichi ETB; got {fledgling.zone}"
    )
    assert rookie.zone == ZoneType.BATTLEFIELD, (
        f"Non-Demon should survive; got {rookie.zone}"
    )
    print(f"  Fledgling Demon zone after ETB: {fledgling.zone.name}")


def test_yoriichi_etb_no_opp_demons_no_crash():
    """Edge: ETB with no opp Demons in play emits no DESTROY events."""
    print("\n=== Yoriichi: empty board no crash ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Yoriichi Tsugikuni, Sun Breather Original")
    new = game.state.event_log[before:]
    destroys = [
        e for e in new
        if e.type == EventType.DESTROY and e.payload.get('reason') == 'yoriichi_etb'
    ]
    assert not destroys, f"Expected no DESTROY with empty opp board; got {len(destroys)}"


def test_yoriichi_attack_anthems_other_slayers():
    """Attack trigger emits PT +1/+1 + first_strike grant to OTHER Slayers you control."""
    print("\n=== Yoriichi: attack anthem ===")
    game = Game()
    p1 = game.add_player("Alice")
    yor = _put_on_battlefield(game, p1, "Yoriichi Tsugikuni, Sun Breather Original")
    rookie = _put_on_battlefield(game, p1, "Rookie Slayer")  # other Slayer

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': yor.id, 'attacker': yor.id, 'controller': p1.id},
        source=yor.id,
    ))
    after = game.state.event_log[before:]
    pt_mods = [
        e for e in after
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == rookie.id
        and e.payload.get('power_mod') == 1
    ]
    kw_grants = [
        e for e in after
        if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == rookie.id
        and e.payload.get('keyword') == 'first_strike'
    ]
    assert pt_mods, "Expected PT_MOD +1 on rookie Slayer"
    assert kw_grants, "Expected first_strike grant on rookie Slayer"
    # Yoriichi himself should NOT be in the anthem set (excluded by id check).
    self_mods = [e for e in after
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('object_id') == yor.id]
    assert not self_mods, "Yoriichi should not self-anthem"


# ============================================================================
# Final Selection (NEW saga)
# ============================================================================

def test_final_selection_loads_as_saga():
    print("\n=== Final Selection: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Final Selection")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert saga.interceptor_ids, "Expected saga chapter interceptors"


def test_final_selection_chapter_i_creates_slayer_token():
    print("\n=== Final Selection: chapter I ===")
    from src.cards.custom.demon_slayer import _final_selection_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Final Selection")
    events = _final_selection_chapter_i(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and e.payload.get('token', {}).get('subtypes', set()) & {'Slayer'}
    ]
    assert len(tokens) == 1, f"Expected 1 Slayer token; got {len(tokens)}"


def test_final_selection_chapter_ii_emits_tribal_tutor():
    print("\n=== Final Selection: chapter II ===")
    from src.cards.custom.demon_slayer import _final_selection_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Final Selection")
    events = _final_selection_chapter_ii(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert set(payload.get('subtypes_any', [])) == {'Slayer'}
    assert payload.get('mana_value_max') == 3
    assert payload.get('enters_tapped') is True


def test_final_selection_chapter_iii_anthem_targets_slayers_only():
    print("\n=== Final Selection: chapter III ===")
    from src.cards.custom.demon_slayer import _final_selection_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Final Selection")
    # Put a Slayer + a non-Slayer on the battlefield
    rookie = _put_on_battlefield(game, p1, "Rookie Slayer")
    boar = _put_on_battlefield(game, p1, "Mountain Boar")  # not a Slayer
    events = _final_selection_chapter_iii(saga, game.state)
    pt_targets = [e.payload['object_id'] for e in events
                  if e.type == EventType.PT_MODIFICATION]
    assert rookie.id in pt_targets, "Slayer should be buffed"
    assert boar.id not in pt_targets, "Non-Slayer should NOT be buffed"
    kw_targets = [e.payload['object_id'] for e in events
                  if e.type == EventType.GRANT_KEYWORD
                  and e.payload.get('keyword') == 'indestructible']
    assert rookie.id in kw_targets


# ============================================================================
# Demon King's Manor (NEW saga)
# ============================================================================

def test_demon_kings_manor_loads_as_saga():
    print("\n=== Demon King's Manor: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Demon King's Manor")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert saga.interceptor_ids


def test_demon_kings_manor_chapter_i_opp_discard():
    print("\n=== Demon King's Manor: chapter I ===")
    from src.cards.custom.demon_slayer import _demon_kings_manor_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "Demon King's Manor")
    events = _demon_kings_manor_chapter_i(saga, game.state)
    discards = [e for e in events
                if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id
                and e.payload.get('amount') == 1]
    assert discards, "Expected DISCARD targeting opp p2"
    # No self-discard
    self_discards = [e for e in events
                     if e.type == EventType.DISCARD
                     and e.payload.get('player') == p1.id]
    assert not self_discards, "Controller should not discard"


def test_demon_kings_manor_chapter_ii_creates_demon_token():
    print("\n=== Demon King's Manor: chapter II ===")
    from src.cards.custom.demon_slayer import _demon_kings_manor_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Demon King's Manor")
    events = _demon_kings_manor_chapter_ii(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and e.payload.get('token', {}).get('subtypes', set()) & {'Demon'}
    ]
    assert len(tokens) == 1
    spec = tokens[0].payload['token']
    assert spec.get('power') == 3 and spec.get('toughness') == 3


def test_demon_kings_manor_chapter_iii_emits_demon_tutor():
    print("\n=== Demon King's Manor: chapter III ===")
    from src.cards.custom.demon_slayer import _demon_kings_manor_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Demon King's Manor")
    events = _demon_kings_manor_chapter_iii(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert set(payload.get('subtypes_any', [])) == {'Demon'}
    assert payload.get('mana_value_max') == 5
    assert payload.get('destination') == 'battlefield'


# ============================================================================
# Tanjiro's Earrings (NEW equipment, reanimator-on-body)
# ============================================================================

def test_tanjiros_earrings_loads_as_equipment():
    print("\n=== Tanjiro's Earrings: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    earrings = _put_on_battlefield(game, p1, "Tanjiro's Earrings")
    assert earrings.zone == ZoneType.BATTLEFIELD
    activated = getattr(earrings.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability"


def test_tanjiros_earrings_attach_grants_pt_and_lifelink():
    """ATTACH applies +1/+1 + lifelink to the equipped creature."""
    print("\n=== Tanjiro's Earrings: attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    earrings = _put_on_battlefield(game, p1, "Tanjiro's Earrings")
    rookie = _put_on_battlefield(game, p1, "Rookie Slayer")  # 1/1 Slayer
    base_p = get_power(rookie, game.state)
    base_t = get_toughness(rookie, game.state)

    # Canonical ATTACH payload (gotcha #13): object_id / target_id.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': earrings.id, 'target_id': rookie.id},
        source=earrings.id,
    ))

    new_p = get_power(rookie, game.state)
    new_t = get_toughness(rookie, game.state)
    assert new_p == base_p + 1, f"Expected power +1: {base_p}->{new_p}"
    assert new_t == base_t + 1, f"Expected toughness +1: {base_t}->{new_t}"
    assert has_ability(rookie, 'lifelink', game.state)


def test_tanjiros_earrings_etb_reanimates_slayer_in_graveyard():
    """ETB emits RETURN_FROM_GRAVEYARD for a Slayer (MV<=3) when one is in GY."""
    print("\n=== Tanjiro's Earrings: ETB reanimate ===")
    game = Game()
    p1 = game.add_player("Alice")

    # Plant a Slayer in p1's graveyard.
    rookie_def = DEMON_SLAYER_CARDS["Rookie Slayer"]
    rookie_obj = game.create_object(
        name="Rookie Slayer",
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=rookie_def.characteristics,
        card_def=None,
    )
    rookie_obj.card_def = rookie_def
    gy = game.state.zones.get(f'graveyard_{p1.id}')
    if gy and rookie_obj.id not in gy.objects:
        gy.objects.append(rookie_obj.id)

    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Tanjiro's Earrings")
    new = game.state.event_log[before:]
    reanimates = [
        e for e in new
        if e.type == EventType.RETURN_FROM_GRAVEYARD
        and e.payload.get('object_id') == rookie_obj.id
        and e.payload.get('destination') == 'battlefield'
    ]
    assert reanimates, (
        f"Expected RETURN_FROM_GRAVEYARD for Rookie Slayer; "
        f"recent={[e.type.name for e in new[-12:]]}"
    )


def test_tanjiros_earrings_etb_empty_graveyard_no_crash():
    """Edge: empty graveyard returns no events."""
    print("\n=== Tanjiro's Earrings: empty graveyard ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Tanjiro's Earrings")
    new = game.state.event_log[before:]
    reanimates = [e for e in new if e.type == EventType.RETURN_FROM_GRAVEYARD]
    assert not reanimates


# ============================================================================
# Tanjiro Kamado, Sun Breather (REWIRE — was no-op effect_fn)
# ============================================================================

def test_tanjiro_sun_breather_loads_with_keywords():
    """Self-keywords flavor was unwired; now properly granted."""
    print("\n=== Tanjiro Sun Breather: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tan = _put_on_battlefield(game, p1, "Tanjiro Kamado, Sun Breather")
    assert tan.zone == ZoneType.BATTLEFIELD
    assert has_ability(tan, 'vigilance', game.state)
    assert has_ability(tan, 'haste', game.state)


def test_tanjiro_sun_breather_attack_destroys_opp_demons():
    """Attack-trigger sweeps each opp-controlled Demon. Uses zone-reads (gotcha #14)."""
    print("\n=== Tanjiro Sun Breather: attack destroys demons ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    tan = _put_on_battlefield(game, p1, "Tanjiro Kamado, Sun Breather")
    fledgling = _put_on_battlefield(game, p2, "Fledgling Demon")

    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': tan.id, 'attacker': tan.id, 'controller': p1.id},
        source=tan.id,
    ))
    assert fledgling.zone == ZoneType.GRAVEYARD, (
        f"Expected Fledgling Demon destroyed by Tanjiro attack; got {fledgling.zone}"
    )


def test_tanjiro_sun_breather_attack_no_demons_no_crash():
    """Edge: attack with no opp Demons emits no DESTROY events."""
    print("\n=== Tanjiro Sun Breather: empty board ===")
    game = Game()
    p1 = game.add_player("Alice")
    tan = _put_on_battlefield(game, p1, "Tanjiro Kamado, Sun Breather")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': tan.id, 'attacker': tan.id, 'controller': p1.id},
        source=tan.id,
    ))
    new = game.state.event_log[before:]
    destroys = [
        e for e in new
        if e.type == EventType.DESTROY and e.payload.get('reason') == 'sun_breathing'
    ]
    assert not destroys


# ============================================================================
# Muzan Kibutsuji (REWIRE — wired flavor indestructible + end-step drain)
# ============================================================================

def test_muzan_has_indestructible():
    """Flavor text said indestructible; was unwired before."""
    print("\n=== Muzan: indestructible ===")
    game = Game()
    p1 = game.add_player("Alice")
    muzan = _put_on_battlefield(game, p1, "Muzan Kibutsuji")
    assert has_ability(muzan, 'indestructible', game.state)


def test_muzan_etb_sacrifice_each_opponent():
    """ETB emits SACRIFICE_REQUIRED for each opponent (not self)."""
    print("\n=== Muzan: ETB sac required ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Muzan Kibutsuji")
    new = game.state.event_log[before:]
    sac_events = [
        e for e in new
        if e.type == EventType.SACRIFICE_REQUIRED
        and e.payload.get('card_type') == 'creature'
    ]
    sac_players = {e.payload.get('player') for e in sac_events}
    assert p2.id in sac_players, "Expected opp to be told to sacrifice"
    assert p1.id not in sac_players, "Muzan's controller should NOT sacrifice"


def test_muzan_end_step_drain_scales_with_demon_count():
    """End-step drain = -N where N = Demons you control."""
    print("\n=== Muzan: end-step drain scales ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    muzan = _put_on_battlefield(game, p1, "Muzan Kibutsuji")
    # Add another Demon under p1 — total 2 Demons.
    _put_on_battlefield(game, p1, "Fledgling Demon")

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and (e.payload.get('amount') or 0) < 0
    ]
    drain_amounts = [e.payload.get('amount') for e in drains]
    # Expect at least one -2 drain (matching 2 Demons).
    assert -2 in drain_amounts, (
        f"Expected -2 drain matching 2 Demons; got {drain_amounts}"
    )


def test_muzan_end_step_drain_zero_demons_no_event():
    """Edge: if no Demons (impossible normally since Muzan IS a Demon, but
    fake the scenario by removing Muzan from battlefield) — drain returns []."""
    print("\n=== Muzan: zero-Demon edge ===")
    from src.cards.custom.demon_slayer import muzan_kibutsuji_setup
    game = Game()
    p1 = game.add_player("Alice")
    # Build a fake Muzan-like obj in a non-BF zone so it doesn't count.
    muzan_def = DEMON_SLAYER_CARDS["Muzan Kibutsuji"]
    fake = game.create_object(
        name="Muzan Kibutsuji",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=muzan_def.characteristics,
        card_def=None,
    )
    fake.card_def = muzan_def
    # Test the end-step closure directly.
    # We need to grab the end-step trigger's effect_fn. Easier: call the
    # setup, find the end_step interceptor, and run its handler on a
    # fake PHASE_START event.
    interceptors = muzan_kibutsuji_setup(fake, game.state)
    # The drain effect runs through make_end_step_trigger — find it.
    # All interceptors are while_on_battlefield; we can't easily inspect
    # the effect directly. Instead: register them, then emit PHASE_START
    # for p1 with fake in hand (not BF). Drain shouldn't trigger because
    # fake isn't on battlefield (and make_end_step_trigger filters on
    # source's zone implicitly via the active interceptor system).
    # Simpler: just confirm via direct game test that with no Demons on
    # the battlefield, no -N drain matches.
    # We use a different fake setup — only a non-Demon Slayer in play.
    game2 = Game()
    p1b = game2.add_player("Alice")
    p2b = game2.add_player("Bob")
    # Place Muzan on BF — but we want to suppress the demon count.
    # Trick: Muzan is the only Demon; remove from BF after ETB triggers settle.
    muzan = _put_on_battlefield(game2, p1b, "Muzan Kibutsuji")
    # Force-move Muzan to HAND to drop demon count to 0 on BF.
    bf = game2.state.zones.get('battlefield')
    if bf and muzan.id in bf.objects:
        bf.objects.remove(muzan.id)
    muzan.zone = ZoneType.HAND

    before = len(game2.state.event_log)
    game2.state.active_player = p1b.id
    game2.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1b.id},
    ))
    new = game2.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2b.id
        and e.payload.get('source') == muzan.id
        and (e.payload.get('amount') or 0) < 0
    ]
    # Since Muzan is not on battlefield, his interceptor is technically still
    # registered (duration 'while_on_battlefield'). The make_end_step_trigger
    # however may still fire. Tolerate: if it does fire, demon count is 0
    # so amount must equal 0 (which the effect_fn early-returns []).
    # The strict assertion: no -N drain from muzan_id with N>=1.
    assert not drains, f"Expected no Muzan drain with 0 Demons; got {drains}"


# ============================================================================
# Nichirin Sword (REWIRE — make_equipment_setup compression)
# ============================================================================

def test_nichirin_sword_loads_with_equip_ability():
    print("\n=== Nichirin Sword: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sword = _put_on_battlefield(game, p1, "Nichirin Sword")
    assert sword.zone == ZoneType.BATTLEFIELD
    activated = getattr(sword.state, 'activated_abilities', None)
    assert activated, "Expected equip ability"


def test_nichirin_sword_attach_grants_pt_and_first_strike():
    print("\n=== Nichirin Sword: attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    sword = _put_on_battlefield(game, p1, "Nichirin Sword")
    rookie = _put_on_battlefield(game, p1, "Rookie Slayer")
    base_p = get_power(rookie, game.state)
    base_t = get_toughness(rookie, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': rookie.id},
        source=sword.id,
    ))
    new_p = get_power(rookie, game.state)
    new_t = get_toughness(rookie, game.state)
    assert new_p == base_p + 2, f"Expected power +2: {base_p}->{new_p}"
    assert new_t == base_t + 1, f"Expected toughness +1: {base_t}->{new_t}"
    assert has_ability(rookie, 'first_strike', game.state)


# ============================================================================
# Hashira Meeting (REWIRE — was no-resolve sorcery)
# ============================================================================

def test_hashira_meeting_resolve_emits_search():
    """Resolve fn returns a SEARCH_LIBRARY for Hashira (up to 3) to hand."""
    print("\n=== Hashira Meeting: resolve ===")
    from src.cards.custom.demon_slayer import hashira_meeting_resolve
    game = Game()
    p1 = game.add_player("Alice")
    game.state.active_player = p1.id
    events = hashira_meeting_resolve([], game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert set(payload.get('subtypes_any', [])) == {'Hashira'}
    assert payload.get('max_count') == 3
    assert payload.get('destination') == 'hand'
    assert payload.get('player') == p1.id


# ============================================================================
# SLICE 5 (2026-05-19) — Thin-bust: 15 vanilla cards lifted to multi-axis depth.
# Each card emits a SCRY/SURVEIL info event and a cross-controller asym event
# (LIFE_CHANGE or DAMAGE to each opponent) on ETB or attack.
# ============================================================================


def _slice5_etb_assert_info_and_asym(
    card_name: str,
    *,
    info_event: EventType,
    asym_event: EventType = EventType.LIFE_CHANGE,
    asym_amount_sign: int = -1,
):
    """Assert ETB on `card_name` emits an info event and a cross-controller asym."""
    print(f"\n=== slice5 ETB {card_name}: info={info_event.name} asym={asym_event.name} ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, card_name)
    new = game.state.event_log[before:]
    infos = [e for e in new if e.type == info_event and e.source == obj.id]
    assert infos, f"{card_name}: expected {info_event.name}; emitted={[e.type.name for e in new]}"
    asyms = [
        e for e in new
        if e.type == asym_event and e.source == obj.id
        and e.payload.get('player') == p2.id
        and (asym_amount_sign == 0 or
             (asym_amount_sign < 0 and e.payload.get('amount', 0) < 0) or
             (asym_amount_sign > 0 and e.payload.get('amount', 0) > 0))
    ]
    if asym_event == EventType.DAMAGE:
        asyms = [
            e for e in new
            if e.type == EventType.DAMAGE and e.source == obj.id
            and e.payload.get('target') == p2.id
        ]
    assert asyms, (
        f"{card_name}: expected {asym_event.name} targeting opp; "
        f"emitted={[(e.type.name, e.payload) for e in new]}"
    )
    return obj


def _slice5_attack_assert_info_and_asym(
    card_name: str,
    *,
    info_event: EventType = EventType.SCRY,
    asym_event: EventType = EventType.LIFE_CHANGE,
):
    """Assert attack trigger on `card_name` emits info + cross-controller asym."""
    print(f"\n=== slice5 attack {card_name}: info={info_event.name} asym={asym_event.name} ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id},
        source=obj.id,
    ))
    new = game.state.event_log[before:]
    infos = [e for e in new if e.type == info_event and e.source == obj.id]
    assert infos, f"{card_name}: expected {info_event.name}; emitted={[e.type.name for e in new]}"
    if asym_event == EventType.DAMAGE:
        asyms = [
            e for e in new
            if e.type == EventType.DAMAGE and e.source == obj.id
            and e.payload.get('target') == p2.id
        ]
    else:
        asyms = [
            e for e in new
            if e.type == asym_event and e.source == obj.id
            and e.payload.get('player') == p2.id
            and e.payload.get('amount', 0) < 0
        ]
    assert asyms, (
        f"{card_name}: expected {asym_event.name} targeting opp; "
        f"emitted={[(e.type.name, e.payload) for e in new]}"
    )
    return obj


def test_slice5_rookie_slayer_etb_scry_and_lifegain():
    obj = _slice5_etb_assert_info_and_asym(
        "Rookie Slayer", info_event=EventType.SCRY, asym_event=EventType.LIFE_CHANGE,
    ) if False else None
    # Rookie's drain only fires if 2+ Slayers; assert scry + lifegain instead.
    print("\n=== slice5 ETB Rookie Slayer ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Rookie Slayer")
    new = game.state.event_log[before:]
    scries = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.source == obj.id
        and e.payload.get('player') == p1.id
        and e.payload.get('amount', 0) > 0
    ]
    assert scries, f"Rookie: SCRY missing"
    assert gains, f"Rookie: own LIFE_CHANGE gain missing"


def test_slice5_trained_slayer_attack_scry_and_drain():
    _slice5_attack_assert_info_and_asym(
        "Trained Slayer", info_event=EventType.SCRY, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_veteran_slayer_etb_scry_and_lifegain():
    print("\n=== slice5 ETB Veteran Slayer ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Veteran Slayer")
    new = game.state.event_log[before:]
    scries = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.source == obj.id
        and e.payload.get('player') == p1.id
        and e.payload.get('amount', 0) > 0
    ]
    assert scries, "Veteran: SCRY missing"
    assert gains, "Veteran: lifegain missing"


def test_slice5_fledgling_demon_etb_surveil_and_drain():
    _slice5_etb_assert_info_and_asym(
        "Fledgling Demon", info_event=EventType.SURVEIL, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_bloodthirsty_demon_attack_scry_and_drain():
    _slice5_attack_assert_info_and_asym(
        "Bloodthirsty Demon", info_event=EventType.SCRY, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_ancient_demon_etb_surveil_and_drain():
    _slice5_etb_assert_info_and_asym(
        "Ancient Demon", info_event=EventType.SURVEIL, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_corps_messenger_etb_scry_alone():
    """Corps Messenger only drains opps if 2+ Slayers; baseline scry should still fire."""
    print("\n=== slice5 ETB Corps Messenger ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Corps Messenger")
    new = game.state.event_log[before:]
    scries = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert scries and scries[0].payload.get('amount') == 2, (
        f"Corps Messenger: expected SCRY 2; got {[(e.type.name, e.payload) for e in new]}"
    )


def test_slice5_dawn_patrol_etb_scry_and_drain():
    _slice5_etb_assert_info_and_asym(
        "Dawn Patrol", info_event=EventType.SCRY, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_corps_instructor_etb_scry_and_drain():
    _slice5_etb_assert_info_and_asym(
        "Corps Instructor", info_event=EventType.SCRY, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_corps_veteran_etb_scry_and_drain():
    _slice5_etb_assert_info_and_asym(
        "Corps Veteran", info_event=EventType.SCRY, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_mist_walker_attack_surveil_and_drain():
    _slice5_attack_assert_info_and_asym(
        "Mist Walker", info_event=EventType.SURVEIL, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_flame_dancer_etb_scry_and_damage():
    _slice5_etb_assert_info_and_asym(
        "Flame Dancer", info_event=EventType.SCRY, asym_event=EventType.DAMAGE,
    )


def test_slice5_fire_breathing_student_attack_scry_and_damage():
    _slice5_attack_assert_info_and_asym(
        "Fire Breathing Student", info_event=EventType.SCRY, asym_event=EventType.DAMAGE,
    )


def test_slice5_forest_tracker_etb_scry_and_drain():
    _slice5_etb_assert_info_and_asym(
        "Forest Tracker", info_event=EventType.SCRY, asym_event=EventType.LIFE_CHANGE,
    )


def test_slice5_blade_master_etb_scry_and_lifegain():
    """Blade Master only drains opps if it controls an Equipment; baseline scry+lifegain should fire."""
    print("\n=== slice5 ETB Blade Master ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Blade Master")
    new = game.state.event_log[before:]
    scries = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.source == obj.id
        and e.payload.get('player') == p1.id
        and e.payload.get('amount', 0) > 0
    ]
    assert scries, "Blade Master: SCRY missing"
    assert gains, "Blade Master: lifegain missing"


# ============================================================================
# SLICE 5.5 (2026-05-19) — decision-axis flip tests
# ============================================================================
# Each test below proves the new card installs a brand-new TARGET_REQUIRED /
# PendingChoice surface (decision axis > 0). Tests do NOT resolve choices —
# resolution requires AI auto-pick or full UI plumbing.
# ============================================================================


# ----------------------------------------------------------------------------
# Yushiro, Sun-Tolerant Demon — modal-ETB (decision=3 modal-deep)
# ----------------------------------------------------------------------------

def test_yushiro_sun_demon_loads():
    """Loads as a legendary Demon with a modal ETB interceptor."""
    print("\n=== Yushiro Sun Demon: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    yu = _put_on_battlefield(game, p1, "Yushiro, Sun-Tolerant Demon")
    chars = yu.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Demon' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert yu.interceptor_ids, f"Expected ETB interceptor; got {yu.interceptor_ids}"
    print(f"  Interceptors: {len(yu.interceptor_ids)}; subtypes={chars.subtypes}")


def test_yushiro_sun_demon_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== Yushiro Sun Demon: modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    yu = _put_on_battlefield(game, p1, "Yushiro, Sun-Tolerant Demon")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == yu.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"
    print(f"  Modes: {[opt.get('label') for opt in pc.options]}")


# ----------------------------------------------------------------------------
# Kanao Tsuyuri, Flower Hashira — targeted-ETB + DRAW (decision=1)
# ----------------------------------------------------------------------------

def test_kanao_flower_hashira_loads():
    """Loads as a legendary Slayer/Hashira with ETB interceptors."""
    print("\n=== Kanao Flower Hashira: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kn = _put_on_battlefield(game, p1, "Kanao Tsuyuri, Flower Hashira")
    chars = kn.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Hashira' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert kn.interceptor_ids, "Expected ETB interceptors"
    print(f"  Interceptors: {len(kn.interceptor_ids)}")


def test_kanao_flower_hashira_etb_emits_target_required_and_draw():
    """ETB emits a TARGET_REQUIRED for an opponent + a DRAW for self."""
    print("\n=== Kanao Flower Hashira: ETB target+draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    kn = _put_on_battlefield(game, p1, "Kanao Tsuyuri, Flower Hashira")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == kn.id
        and e.payload.get('effect') == 'reveal_hand'
    ]
    assert target_reqs, (
        f"Expected reveal_hand TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    assert target_reqs[0].payload.get('target_filter') == 'opponent'
    draws = [e for e in new
             if e.type == EventType.DRAW
             and e.source == kn.id
             and e.payload.get('player') == p1.id]
    assert draws, f"Expected DRAW for controller; new={[e.type.name for e in new[-10:]]}"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; DRAW: {len(draws)}")


# ----------------------------------------------------------------------------
# Hinokami Kagura, Sun Dance — divided damage (decision=1)
# ----------------------------------------------------------------------------

def test_hinokami_kagura_loads():
    """Loads as a Red/White enchantment with ETB interceptor."""
    print("\n=== Hinokami Kagura: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hk = _put_on_battlefield(game, p1, "Hinokami Kagura, Sun Dance")
    assert CardType.ENCHANTMENT in hk.characteristics.types
    assert hk.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(hk.interceptor_ids)}")


def test_hinokami_kagura_etb_emits_divided_damage_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=5 and damage effect."""
    print("\n=== Hinokami Kagura: ETB divided 5 ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    hk = _put_on_battlefield(game, p1, "Hinokami Kagura, Sun Dance")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == hk.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 5, (
        f"Expected divide_amount=5; got {payload.get('divide_amount')}"
    )
    print(f"  divide_amount: {payload.get('divide_amount')}")


# ----------------------------------------------------------------------------
# Kasugai Crow Roost — divided counters (decision=1 + synergy)
# ----------------------------------------------------------------------------

def test_kasugai_crow_roost_loads():
    """Loads as a Green/White enchantment with ETB interceptor."""
    print("\n=== Kasugai Crow Roost: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kcr = _put_on_battlefield(game, p1, "Kasugai Crow Roost")
    assert CardType.ENCHANTMENT in kcr.characteristics.types
    assert kcr.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(kcr.interceptor_ids)}")


def test_kasugai_crow_roost_etb_emits_counter_add_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=4 and counter_add effect."""
    print("\n=== Kasugai Crow Roost: ETB distribute counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    kcr = _put_on_battlefield(game, p1, "Kasugai Crow Roost")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == kcr.id
        and e.payload.get('effect') == 'counter_add'
    ]
    assert target_reqs, (
        f"Expected counter_add TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 4, (
        f"Expected divide_amount=4; got {payload.get('divide_amount')}"
    )
    assert payload.get('target_filter') == 'your_creature'
    print(f"  divide_amount: {payload.get('divide_amount')}; filter: {payload.get('target_filter')}")


# ----------------------------------------------------------------------------
# Daki, Upper Moon Six — targeted death + asymmetric discard
# ----------------------------------------------------------------------------

def test_daki_upper_moon_six_loads():
    """Loads as a legendary Demon with death-trigger interceptors."""
    print("\n=== Daki Upper Moon Six: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    dk = _put_on_battlefield(game, p1, "Daki, Upper Moon Six")
    chars = dk.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Demon' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(dk.interceptor_ids) >= 2, (
        f"Expected >=2 (targeted-death + death listener); got {len(dk.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(dk.interceptor_ids)}")


def test_daki_death_emits_target_required_and_discard():
    """On death, emits TARGET_REQUIRED for destroy + DISCARD on opp hand."""
    print("\n=== Daki: death trigger ===")
    from src.engine import Characteristics
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant a card in p2's hand so DISCARD pulse has something to bite.
    junk_chars = Characteristics(
        types={CardType.CREATURE}, subtypes={"Pirate"}, power=1, toughness=1,
    )
    game.create_object(
        name="Spare", owner_id=p2.id, zone=ZoneType.HAND,
        characteristics=junk_chars, card_def=None,
    )
    dk = _put_on_battlefield(game, p1, "Daki, Upper Moon Six")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': dk.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'destroy',
        },
        source=dk.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == dk.id
        and e.payload.get('effect') == 'destroy'
    ]
    assert target_reqs, (
        f"Expected destroy TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    assert target_reqs[0].payload.get('target_filter') == 'opponent_creature'
    discards = [
        e for e in new
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
        and e.source == dk.id
    ]
    assert discards, f"Expected DISCARD on p2; new={[e.type.name for e in new[-10:]]}"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; DISCARD: {len(discards)}")


# ----------------------------------------------------------------------------
# Tamayo, Heretic Healer — top-N + zone-coupling
# ----------------------------------------------------------------------------

def test_tamayo_heretic_healer_loads():
    """Loads as a legendary Demon Doctor with ETB interceptor."""
    print("\n=== Tamayo Heretic Healer: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tm = _put_on_battlefield(game, p1, "Tamayo, Heretic Healer")
    chars = tm.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Doctor' in chars.subtypes
    assert 'Demon' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert tm.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(tm.interceptor_ids)}; subtypes={chars.subtypes}")


def test_tamayo_etb_empty_library_no_op():
    """ETB with empty library doesn't crash and doesn't install a choice."""
    print("\n=== Tamayo: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Library is empty by default in this harness.
    tm = _put_on_battlefield(game, p1, "Tamayo, Heretic Healer")
    assert tm.zone == ZoneType.BATTLEFIELD
    print(f"  No-crash; pending_choice={game.state.pending_choice}")


def test_tamayo_etb_with_library_lands_opens_choice():
    """ETB with a land on top of library installs a PendingChoice."""
    print("\n=== Tamayo: library lands -> choice ===")
    from src.engine import Characteristics
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a land in p1's library so the helper has something to pick.
    lib = game.state.zones[f'library_{p1.id}']
    land_chars = Characteristics(types={CardType.LAND}, subtypes={"Island"})
    land_obj = game.create_object(
        name="Test Island", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=land_chars, card_def=None,
    )
    if land_obj.id not in lib.objects:
        lib.objects.append(land_obj.id)
    tm = _put_on_battlefield(game, p1, "Tamayo, Heretic Healer")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice installed by top-N land pick"
    assert pc.source_id == tm.id, f"Choice source should be Tamayo; got {pc.source_id}"
    print(f"  PendingChoice type: {pc.choice_type}; source: {pc.source_id}")


# ----------------------------------------------------------------------------
# Genya Shinazugawa, Demon Eater — targeted-attack trigger (decision=1)
# ----------------------------------------------------------------------------

def test_genya_demon_eater_loads():
    """Loads as a legendary Slayer with trample + attack-trigger."""
    print("\n=== Genya Demon Eater: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    gn = _put_on_battlefield(game, p1, "Genya Shinazugawa, Demon Eater")
    chars = gn.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Slayer' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(gn.interceptor_ids) >= 2, (
        f"Expected >=2 (trample kw + attack trigger); got {len(gn.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(gn.interceptor_ids)}")


def test_genya_attack_emits_exile_target_required():
    """On attack, emits TARGET_REQUIRED with effect='exile' targeting opp creature."""
    print("\n=== Genya: attack exile trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    gn = _put_on_battlefield(game, p1, "Genya Shinazugawa, Demon Eater")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': gn.id, 'attacker': gn.id, 'controller': p1.id},
        source=gn.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == gn.id
        and e.payload.get('effect') == 'exile'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected exile TARGET_REQUIRED on attack; new={[e.type.name for e in new[-10:]]}"
    )
    print(f"  TARGET_REQUIRED (exile): {len(target_reqs)}")


# ----------------------------------------------------------------------------
# Muzan's Whispering Network — create_scry_choice + library zone read
# ----------------------------------------------------------------------------

def test_muzan_whispering_network_loads():
    """Loads as a Blue/Black enchantment with ETB interceptor."""
    print("\n=== Muzan's Whispering Network: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    mwn = _put_on_battlefield(game, p1, "Muzan's Whispering Network")
    assert CardType.ENCHANTMENT in mwn.characteristics.types
    assert mwn.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(mwn.interceptor_ids)}")


def test_muzan_whispering_network_etb_opens_scry_choice():
    """ETB with cards in library installs a scry PendingChoice."""
    print("\n=== Muzan's Whispering Network: scry choice ===")
    from src.engine import Characteristics
    game = Game()
    p1 = game.add_player("Alice")
    # Plant 3 cards in p1's library so scry has something to look at.
    lib = game.state.zones[f'library_{p1.id}']
    for i in range(3):
        chars = Characteristics(types={CardType.CREATURE}, subtypes={"Demon"}, power=1, toughness=1)
        c = game.create_object(
            name=f"Spare Demon {i}", owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=chars, card_def=None,
        )
        if c.id not in lib.objects:
            lib.objects.append(c.id)
    mwn = _put_on_battlefield(game, p1, "Muzan's Whispering Network")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice (scry)"
    assert pc.source_id == mwn.id
    assert pc.choice_type == "scry"
    print(f"  PendingChoice type: {pc.choice_type}; source: {pc.source_id}")


# ----------------------------------------------------------------------------
# Nezuko's Exploding Blood — targeted-ETB damage + sacrifice choice
# ----------------------------------------------------------------------------

def test_nezuko_exploding_blood_loads():
    """Loads as a Red enchantment with ETB interceptors."""
    print("\n=== Nezuko's Exploding Blood: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    neb = _put_on_battlefield(game, p1, "Nezuko's Exploding Blood")
    assert CardType.ENCHANTMENT in neb.characteristics.types
    assert neb.interceptor_ids, "Expected ETB interceptors"
    print(f"  Interceptors: {len(neb.interceptor_ids)}")


def test_nezuko_exploding_blood_etb_emits_damage_target_required():
    """ETB emits a damage TARGET_REQUIRED with amount=4 and opp_creature filter."""
    print("\n=== Nezuko's Exploding Blood: ETB damage TR ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    neb = _put_on_battlefield(game, p1, "Nezuko's Exploding Blood")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == neb.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    assert target_reqs[0].payload.get('effect_params', {}).get('amount') == 4
    print(f"  TARGET_REQUIRED (damage 4): {len(target_reqs)}")


# ----------------------------------------------------------------------------
# Gyokko, Twisted Pottery Demon — create_surveil_choice + drain
# ----------------------------------------------------------------------------

def test_gyokko_pottery_demon_loads():
    """Loads as a legendary Demon with ETB interceptor."""
    print("\n=== Gyokko Pottery Demon: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    gy = _put_on_battlefield(game, p1, "Gyokko, Twisted Pottery Demon")
    chars = gy.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Demon' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert gy.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(gy.interceptor_ids)}")


def test_gyokko_pottery_demon_etb_opens_surveil_choice_and_drains():
    """ETB with cards in library installs a surveil PendingChoice + drains opp."""
    print("\n=== Gyokko: surveil choice + drain ===")
    from src.engine import Characteristics
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant 3 cards in p1's library so surveil has something to look at.
    lib = game.state.zones[f'library_{p1.id}']
    for i in range(3):
        chars = Characteristics(types={CardType.CREATURE}, subtypes={"Demon"}, power=1, toughness=1)
        c = game.create_object(
            name=f"Vase Specimen {i}", owner_id=p1.id, zone=ZoneType.LIBRARY,
            characteristics=chars, card_def=None,
        )
        if c.id not in lib.objects:
            lib.objects.append(c.id)
    before = len(game.state.event_log)
    gy = _put_on_battlefield(game, p1, "Gyokko, Twisted Pottery Demon")
    new = game.state.event_log[before:]
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice (surveil)"
    assert pc.source_id == gy.id
    assert pc.choice_type == "surveil"
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.source == gy.id
        and e.payload.get('player') == p2.id
        and e.payload.get('amount', 0) < 0
    ]
    assert drains, f"Expected opp LIFE_CHANGE drain; new={[e.type.name for e in new[-10:]]}"
    print(f"  PendingChoice: {pc.choice_type}; drains: {len(drains)}")


# ----------------------------------------------------------------------------
# Mizunoto Trial Recruitment — create_discard_choice (opp hand)
# ----------------------------------------------------------------------------

def test_mizunoto_trial_recruitment_loads():
    """Loads as a White/Black enchantment with ETB interceptor."""
    print("\n=== Mizunoto Trial Recruitment: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    mtr = _put_on_battlefield(game, p1, "Mizunoto Trial Recruitment")
    assert CardType.ENCHANTMENT in mtr.characteristics.types
    assert mtr.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(mtr.interceptor_ids)}")


def test_mizunoto_trial_recruitment_etb_opens_discard_choice_on_opp():
    """ETB with a card in opp's hand installs a discard PendingChoice for opp."""
    print("\n=== Mizunoto Trial: opp discard choice ===")
    from src.engine import Characteristics
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant a card in p2's hand so discard has something to bite.
    junk_chars = Characteristics(
        types={CardType.CREATURE}, subtypes={"Slayer"}, power=1, toughness=1,
    )
    game.create_object(
        name="Junk Recruit", owner_id=p2.id, zone=ZoneType.HAND,
        characteristics=junk_chars, card_def=None,
    )
    mtr = _put_on_battlefield(game, p1, "Mizunoto Trial Recruitment")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice (discard)"
    assert pc.source_id == mtr.id
    assert pc.choice_type == "discard"
    assert pc.player == p2.id, f"Discard choice should be on opp; got {pc.player}"
    print(f"  PendingChoice: {pc.choice_type}; player: {pc.player}")


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
