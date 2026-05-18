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
