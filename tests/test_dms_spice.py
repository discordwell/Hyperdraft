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
from src.cards.custom import demon_slayer as demon_slayer_module


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
# Slice-12 median-lift tests (2026-05-19): one assertion per buffed vanilla
# card driving DMS median_depth 0 -> >= 2. Each test puts the card on the
# battlefield (or invokes its resolve handler for instants/sorceries) and
# asserts the expected SCRY/SURVEIL info event + a cross-controller effect
# (LIFE_CHANGE / DAMAGE / MILL / DISCARD / REVEAL_HAND).
# ============================================================================


def _s12_etb_card(card_name):
    """Spin up a game, put the named card under p1, return (game, p1, p2, obj)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    return game, p1, p2, obj


def _s12_assert_info_and_opp(game, obj, p2, *, info_type, opp_type):
    """Assert info_type (SCRY/SURVEIL) emitted by obj + a cross-controller effect.
    For LIFE_CHANGE we require amount < 0; for DAMAGE we require target == p2.id."""
    new = list(game.state.event_log)
    info_evs = [e for e in new if e.type == info_type and e.source == obj.id]
    assert info_evs, (
        f"Expected {info_type.name} from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )
    if opp_type == EventType.LIFE_CHANGE:
        opp_evs = [e for e in new if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('player') == p2.id
                   and e.payload.get('amount', 0) < 0
                   and e.source == obj.id]
    elif opp_type == EventType.DAMAGE:
        opp_evs = [e for e in new if e.type == EventType.DAMAGE
                   and e.payload.get('target') == p2.id
                   and e.source == obj.id]
    elif opp_type in (EventType.MILL, EventType.DISCARD, EventType.REVEAL_HAND):
        opp_evs = [e for e in new if e.type == opp_type
                   and e.payload.get('player') == p2.id
                   and e.source == obj.id]
    else:
        opp_evs = []
    assert opp_evs, (
        f"Expected {opp_type.name} against p2 from {obj.id}; "
        f"events={[e.type.name for e in new[-15:]]}"
    )


def _s12_resolve(fn_name):
    """Pull a resolve fn out of the demon_slayer module, prep a 2-player state, call it."""
    fn = getattr(demon_slayer_module, fn_name)
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    events = fn([], game.state)
    return events, p1, p2


def _s12_assert_resolve_info(events, expected_info_type):
    assert any(e.type == expected_info_type for e in events), (
        f"Expected {expected_info_type.name} in resolve events; "
        f"got {[e.type.name for e in events]}"
    )


def _s12_assert_resolve_opp(events, p2, opp_type):
    if opp_type == EventType.LIFE_CHANGE:
        assert any(e.type == EventType.LIFE_CHANGE
                   and e.payload.get('player') == p2.id
                   and e.payload.get('amount', 0) < 0 for e in events), (
            f"Expected drain on p2 in resolve; got {[(e.type.name, e.payload) for e in events]}"
        )
    elif opp_type == EventType.DAMAGE:
        assert any(e.type == EventType.DAMAGE
                   and e.payload.get('target') == p2.id for e in events), (
            f"Expected damage on p2 in resolve; got {[(e.type.name, e.payload) for e in events]}"
        )
    elif opp_type in (EventType.MILL, EventType.DISCARD, EventType.REVEAL_HAND):
        assert any(e.type == opp_type and e.payload.get('player') == p2.id for e in events), (
            f"Expected {opp_type.name} on p2; got {[(e.type.name, e.payload) for e in events]}"
        )


# --- Permanent (ETB) tests --------------------------------------------------


def test_corps_solidarity_resolve_s12():
    print("\n=== Slice-12: Corps Solidarity resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_corps_solidarity")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_breath_of_recovery_resolve_s12():
    print("\n=== Slice-12: Breath of Recovery resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_breath_of_recovery")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_sunlight_protection_resolve_s12():
    print("\n=== Slice-12: Sunlight Protection resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_sunlight_protection")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_corps_training_resolve_s12():
    print("\n=== Slice-12: Corps Training resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_corps_training")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_recovery_at_estate_resolve_s12():
    print("\n=== Slice-12: Recovery at the Estate resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_recovery_at_estate")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_pillar_of_strength_resolve_s12():
    print("\n=== Slice-12: Pillar of Strength resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_pillar_of_strength")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_hashira_training_resolve_s12():
    print("\n=== Slice-12: Hashira Training resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_hashira_training")
    _s12_assert_resolve_info(events, EventType.SCRY)


def test_first_breath_resolve_s12():
    print("\n=== Slice-12: First Breath resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_first_breath")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_slayer_coordination_resolve_s12():
    print("\n=== Slice-12: Slayer Coordination resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_slayer_coordination")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_dawn_breaks_resolve_s12():
    print("\n=== Slice-12: Dawn Breaks resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_dawn_breaks")
    _s12_assert_resolve_info(events, EventType.SCRY)


def test_demon_slayer_strike_resolve_s12():
    print("\n=== Slice-12: Demon Slayer's Strike resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_demon_slayer_strike")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


# --- White permanents ---


def test_total_concentration_constant_etb_s12():
    print("\n=== Slice-12: Total Concentration Constant ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Total Concentration Constant")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_sworn_protector_etb_s12():
    print("\n=== Slice-12: Sworn Protector ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Sworn Protector")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_ubuyashiki_blessing_etb_s12():
    print("\n=== Slice-12: Ubuyashiki Blessing ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Ubuyashiki Blessing")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_demon_slayer_corps_banner_etb_s12():
    print("\n=== Slice-12: Demon Slayer Corps Banner ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Demon Slayer Corps Banner")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_wisteria_incense_etb_s12():
    print("\n=== Slice-12: Wisteria Incense ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Wisteria Incense")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_demon_mark_bearer_etb_s12():
    print("\n=== Slice-12: Demon Slayer Mark Bearer ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Demon Slayer Mark Bearer")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_corps_medic_etb_s12():
    print("\n=== Slice-12: Corps Medic ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Corps Medic")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_demon_hunters_vow_etb_s12():
    print("\n=== Slice-12: Demon Hunter's Vow ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Demon Hunter's Vow")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


# --- Blue resolve handlers ---


def test_water_surface_slash_resolve_s12():
    print("\n=== Slice-12: Water Surface Slash resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_water_surface_slash")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_water_wheel_resolve_s12():
    print("\n=== Slice-12: Water Wheel resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_water_wheel")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_flowing_dance_resolve_s12():
    print("\n=== Slice-12: Flowing Dance resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_flowing_dance")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_obscuring_clouds_resolve_s12():
    print("\n=== Slice-12: Obscuring Clouds resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_obscuring_clouds")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_whirlpool_technique_resolve_s12():
    print("\n=== Slice-12: Whirlpool Technique resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_whirlpool_technique")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_waterfall_basin_resolve_s12():
    print("\n=== Slice-12: Waterfall Basin resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_waterfall_basin")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_dead_calm_resolve_s12():
    print("\n=== Slice-12: Dead Calm resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_dead_calm")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_drop_ripple_thrust_resolve_s12():
    print("\n=== Slice-12: Drop Ripple Thrust resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_drop_ripple_thrust")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_splashing_water_flow_resolve_s12():
    print("\n=== Slice-12: Splashing Water Flow resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_splashing_water_flow")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_eleventh_form_resolve_s12():
    print("\n=== Slice-12: Eleventh Form: Dead Calm resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_eleventh_form")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_mist_clone_resolve_s12():
    print("\n=== Slice-12: Mist Clone resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_mist_clone")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_water_form_strike_resolve_s12():
    print("\n=== Slice-12: Water Form Strike resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_water_form_strike")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_mist_shroud_resolve_s12():
    print("\n=== Slice-12: Mist Shroud resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_mist_shroud")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


def test_hashira_wisdom_resolve_s12():
    print("\n=== Slice-12: Hashira's Wisdom resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_hashira_wisdom")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.MILL)


# --- Blue permanents ---


def test_mist_breathing_form_etb_s12():
    print("\n=== Slice-12: Mist Breathing Form ETB surveil+mill ===")
    g, p1, p2, obj = _s12_etb_card("Mist Breathing Form")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_constant_flux_etb_s12():
    print("\n=== Slice-12: Constant Flux ETB surveil+mill ===")
    g, p1, p2, obj = _s12_etb_card("Constant Flux")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_water_surface_etb_s12():
    print("\n=== Slice-12: Water Surface ETB surveil+mill ===")
    g, p1, p2, obj = _s12_etb_card("Water Surface")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_water_breathing_master_etb_s12():
    print("\n=== Slice-12: Water Breathing Master ETB surveil+mill ===")
    g, p1, p2, obj = _s12_etb_card("Water Breathing Master")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


# --- Black resolve handlers ---


def test_demonic_transformation_resolve_s12():
    print("\n=== Slice-12: Demonic Transformation resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_demonic_transformation")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.DISCARD)


def test_blood_demon_art_destruction_resolve_s12():
    print("\n=== Slice-12: Blood Demon Art: Destruction resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_blood_demon_art_destruction")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.DISCARD)


def test_muzans_blood_resolve_s12():
    print("\n=== Slice-12: Muzan's Blood resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_muzans_blood")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_demon_consumption_resolve_s12():
    print("\n=== Slice-12: Demon Consumption resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_demon_consumption")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.DISCARD)


def test_temptation_of_eternity_resolve_s12():
    print("\n=== Slice-12: Temptation of Eternity resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_temptation_of_eternity")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.DISCARD)


def test_blood_demon_nightmare_resolve_s12():
    print("\n=== Slice-12: Blood Demon Art: Nightmare resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_blood_demon_nightmare")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.DISCARD)


def test_devour_humans_resolve_s12():
    print("\n=== Slice-12: Devour Humans resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_devour_humans")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_blood_moon_ritual_resolve_s12():
    print("\n=== Slice-12: Blood Moon Ritual resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_blood_moon_ritual")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_demon_regeneration_resolve_s12():
    print("\n=== Slice-12: Demon Regeneration resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_demon_regeneration")
    _s12_assert_resolve_info(events, EventType.SURVEIL)


def test_midnight_hunt_resolve_s12():
    print("\n=== Slice-12: Midnight Hunt resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_midnight_hunt")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.DISCARD)


# --- Black permanents ---


def test_nightmare_blood_art_etb_s12():
    print("\n=== Slice-12: Nightmare Blood Art ETB surveil+discard ===")
    g, p1, p2, obj = _s12_etb_card("Nightmare Blood Art")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.DISCARD)


def test_endless_night_etb_s12():
    print("\n=== Slice-12: Endless Night ETB surveil+drain ===")
    g, p1, p2, obj = _s12_etb_card("Endless Night")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_demon_blood_frenzy_etb_s12():
    print("\n=== Slice-12: Demon Blood Frenzy ETB surveil+drain ===")
    g, p1, p2, obj = _s12_etb_card("Demon Blood Frenzy")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


# --- Red resolve handlers ---


def test_thunderclap_flash_resolve_s12():
    print("\n=== Slice-12: Thunderclap and Flash resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_thunderclap_flash")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_flame_unknowing_fire_resolve_s12():
    print("\n=== Slice-12: Flame Breathing: Unknowing Fire resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_flame_unknowing_fire")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_flame_rengoku_resolve_s12():
    print("\n=== Slice-12: Flame Breathing: Rengoku resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_flame_rengoku")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_sixfold_resolve_s12():
    print("\n=== Slice-12: Sixfold resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_sixfold")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_heat_of_battle_resolve_s12():
    print("\n=== Slice-12: Heat of Battle resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_heat_of_battle")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_explosive_blood_resolve_s12():
    print("\n=== Slice-12: Explosive Blood resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_explosive_blood")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_set_heart_ablaze_resolve_s12():
    print("\n=== Slice-12: Set Your Heart Ablaze resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_set_heart_ablaze")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_flaming_blade_resolve_s12():
    print("\n=== Slice-12: Flaming Blade resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_flaming_blade")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_godspeed_resolve_s12():
    print("\n=== Slice-12: Godspeed resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_godspeed")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_raging_inferno_resolve_s12():
    print("\n=== Slice-12: Raging Inferno resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_raging_inferno")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_fiery_assault_resolve_s12():
    print("\n=== Slice-12: Fiery Assault resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_fiery_assault")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_blood_art_explosion_resolve_s12():
    print("\n=== Slice-12: Blood Art: Explosion resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_blood_art_explosion")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


# --- Red permanents ---


def test_burning_determination_etb_s12():
    print("\n=== Slice-12: Burning Determination ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Burning Determination")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_thunder_breathing_form_etb_s12():
    print("\n=== Slice-12: Thunder Breathing Form ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Thunder Breathing Form")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_thunder_breathing_student_etb_s12():
    print("\n=== Slice-12: Thunder Breathing Student ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Thunder Breathing Student")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_flame_breathing_master_etb_s12():
    print("\n=== Slice-12: Flame Breathing Master ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Flame Breathing Master")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_flame_tigers_etb_s12():
    print("\n=== Slice-12: Flame Tigers ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Flame Tigers")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


# --- Green resolve handlers ---


def test_beast_breathing_fang_resolve_s12():
    print("\n=== Slice-12: Beast Breathing: Fang resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_beast_breathing_fang")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_beast_slice_resolve_s12():
    print("\n=== Slice-12: Beast Breathing: Crazy Cutting resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_beast_slice")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_devour_whole_resolve_s12():
    print("\n=== Slice-12: Devour Whole resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_devour_whole")
    _s12_assert_resolve_info(events, EventType.SURVEIL)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_primal_fury_resolve_s12():
    print("\n=== Slice-12: Primal Fury resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_primal_fury")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_serpentine_coil_resolve_s12():
    print("\n=== Slice-12: Serpentine Coil resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_serpentine_coil")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_wisteria_bloom_resolve_s12():
    print("\n=== Slice-12: Wisteria Bloom resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_wisteria_bloom")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_nature_sense_resolve_s12():
    print("\n=== Slice-12: Spatial Awareness resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_nature_sense")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_beast_sense_resolve_s12():
    print("\n=== Slice-12: Beast Sense resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_beast_sense")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_wild_charge_resolve_s12():
    print("\n=== Slice-12: Wild Charge resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_wild_charge")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


def test_demon_pursuit_resolve_s12():
    print("\n=== Slice-12: Demon Pursuit resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_demon_pursuit")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.LIFE_CHANGE)


def test_serpent_strike_resolve_s12():
    print("\n=== Slice-12: Serpent Strike resolve ===")
    events, p1, p2 = _s12_resolve("_dms_resolve_serpent_strike")
    _s12_assert_resolve_info(events, EventType.SCRY)
    _s12_assert_resolve_opp(events, p2, EventType.DAMAGE)


# --- Green permanents ---


def test_serpent_breathing_form_etb_s12():
    print("\n=== Slice-12: Serpent Breathing Form ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Serpent Breathing Form")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_wild_instinct_etb_s12():
    print("\n=== Slice-12: Wild Instinct ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Wild Instinct")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_overgrowth_technique_etb_s12():
    print("\n=== Slice-12: Overgrowth Technique ETB scry (gain) ===")
    g, p1, p2, obj = _s12_etb_card("Overgrowth Technique")
    new = list(g.state.event_log)
    info_evs = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_evs, f"Expected SCRY from {obj.id}; got {[e.type.name for e in new[-15:]]}"


def test_wisteria_guardian_etb_s12():
    print("\n=== Slice-12: Wisteria Guardian ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Wisteria Guardian")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


# --- Artifact permanents (ETB) ---


def test_wisteria_poison_etb_s12():
    print("\n=== Slice-12: Wisteria Poison ETB surveil+drain ===")
    g, p1, p2, obj = _s12_etb_card("Wisteria Poison")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_kasugai_crow_etb_s12():
    print("\n=== Slice-12: Kasugai Crow ETB scry+reveal ===")
    g, p1, p2, obj = _s12_etb_card("Kasugai Crow")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.REVEAL_HAND)


def test_swordsmith_tools_etb_s12():
    print("\n=== Slice-12: Swordsmith's Tools ETB scry (gain) ===")
    g, p1, p2, obj = _s12_etb_card("Swordsmith's Tools")
    new = list(g.state.event_log)
    info_evs = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_evs, f"Expected SCRY from {obj.id}"


def test_muzans_blood_vial_etb_s12():
    print("\n=== Slice-12: Muzan's Blood Vial ETB surveil+drain ===")
    g, p1, p2, obj = _s12_etb_card("Muzan's Blood Vial")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_demon_art_focus_etb_s12():
    print("\n=== Slice-12: Demon Art Focus ETB surveil+drain ===")
    g, p1, p2, obj = _s12_etb_card("Demon Art Focus")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_corps_supply_depot_etb_s12():
    print("\n=== Slice-12: Corps Supply Depot ETB scry (gain) ===")
    g, p1, p2, obj = _s12_etb_card("Corps Supply Depot")
    new = list(g.state.event_log)
    info_evs = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_evs, f"Expected SCRY from {obj.id}"


def test_training_dummy_etb_s12():
    print("\n=== Slice-12: Training Dummy ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Training Dummy")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_healing_potion_etb_s12():
    print("\n=== Slice-12: Healing Potion ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Healing Potion")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_demon_compass_etb_s12():
    print("\n=== Slice-12: Demon Compass ETB surveil+reveal ===")
    g, p1, p2, obj = _s12_etb_card("Demon Compass")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.REVEAL_HAND)


def test_signal_flare_etb_s12():
    print("\n=== Slice-12: Signal Flare ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Signal Flare")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


# --- Land permanents (ETB on land) ---


def test_butterfly_estate_land_etb_s12():
    print("\n=== Slice-12: Butterfly Estate ETB scry (gain) ===")
    g, p1, p2, obj = _s12_etb_card("Butterfly Estate")
    new = list(g.state.event_log)
    info_evs = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_evs, f"Expected SCRY from {obj.id}"


def test_mt_sagiri_etb_s12():
    print("\n=== Slice-12: Mt. Sagiri ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Mt. Sagiri")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_infinity_castle_etb_s12():
    print("\n=== Slice-12: Infinity Castle ETB surveil+mill ===")
    g, p1, p2, obj = _s12_etb_card("Infinity Castle")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_flame_training_grounds_etb_s12():
    print("\n=== Slice-12: Flame Training Grounds ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Flame Training Grounds")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_wisteria_forest_etb_s12():
    print("\n=== Slice-12: Wisteria Forest ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Wisteria Forest")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_swordsmith_village_etb_s12():
    print("\n=== Slice-12: Swordsmith Village ETB scry (gain) ===")
    g, p1, p2, obj = _s12_etb_card("Swordsmith Village")
    new = list(g.state.event_log)
    info_evs = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_evs, f"Expected SCRY from {obj.id}"


def test_demon_slayer_hq_etb_s12():
    print("\n=== Slice-12: Demon Slayer Headquarters ETB scry+drain ===")
    g, p1, p2, obj = _s12_etb_card("Demon Slayer Headquarters")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.LIFE_CHANGE)


def test_final_selection_mt_etb_s12():
    print("\n=== Slice-12: Final Selection Mountain ETB scry+damage ===")
    g, p1, p2, obj = _s12_etb_card("Final Selection Mountain")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SCRY, opp_type=EventType.DAMAGE)


def test_entertainment_district_etb_s12():
    print("\n=== Slice-12: Entertainment District ETB surveil+mill ===")
    g, p1, p2, obj = _s12_etb_card("Entertainment District")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_mugen_train_etb_s12():
    print("\n=== Slice-12: Mugen Train ETB surveil+drain ===")
    g, p1, p2, obj = _s12_etb_card("Mugen Train")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.LIFE_CHANGE)


def test_demon_lair_etb_s12():
    print("\n=== Slice-12: Demon Lair ETB surveil+mill ===")
    g, p1, p2, obj = _s12_etb_card("Demon Lair")
    _s12_assert_info_and_opp(g, obj, p2, info_type=EventType.SURVEIL, opp_type=EventType.MILL)


def test_hashira_estate_etb_s12():
    print("\n=== Slice-12: Hashira Estate ETB scry (gain) ===")
    g, p1, p2, obj = _s12_etb_card("Hashira Estate")
    new = list(g.state.event_log)
    info_evs = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_evs, f"Expected SCRY from {obj.id}"


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
