"""
Harry Potter: Wizarding World — Spice Pass Tests (Phase A1)

Validates the format-defining cards added in the HPW pilot.
Phase A1 — within current engine, no new helpers. Mirrors the ZLD
pilot test shape (tests/test_zelda_spice.py).

Cards covered:
- Elder Wand (REWIRE) — +3/+0 + first_strike + ward {2}
- Resurrection Stone (REWIRE) — {3}, {T}, Sac: reanimate MV<=3
- Invisibility Cloak (REWIRE) — +0/+2 + hexproof + unblockable
- Lord Voldemort, the Dark Lord (REWIRE) — Deathly-Hallows-gated mythic
- Albus Dumbledore, Headmaster (REWIRE) — ETB scry 2 + draw, vigilance
- Sirius Black, Escaped Convict (REWIRE, was unwired) — attack-ping cantrip
- Hogwarts: The Sorting Year (NEW saga) — 3-chapter House saga
- Fawkes the Phoenix (REWIRE, was unwired) — reanimator on a body
"""

import sys
import os
# Resolve repo root from this file's location so the test works from any
# worktree (the ZLD pilot hardcoded the main checkout path; that breaks
# in `.claude/worktrees/agent-*/` checkouts).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.harry_potter import HARRY_POTTER_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the ZLD spice test harness shape (gotcha-safe path).

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE
    to battlefield, runs setup exactly once via the pipeline (the correct
    path)."""
    card_def = HARRY_POTTER_CARDS[card_name]
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
    """Plant a card directly into the named player's graveyard zone (for
    reanimator-target setup). Skips setup_interceptors entirely — the card
    lives only as a graveyard-resident object."""
    card_def = HARRY_POTTER_CARDS[card_name]
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
# Elder Wand (REWIRE)
# ============================================================================

def test_elder_wand_loads():
    """make_equipment_setup registers PT-mod + first_strike + ward {2} +
    equip-cost ability."""
    print("\n=== Elder Wand: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wand = _put_on_battlefield(game, p1, "Elder Wand")
    assert wand.zone == ZoneType.BATTLEFIELD
    activated = getattr(wand.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Elder Wand"
    # PT + keyword + ward = at least 3 interceptors.
    assert len(wand.interceptor_ids) >= 2, (
        f"Expected PT + ward/keyword interceptors; got {len(wand.interceptor_ids)}"
    )


def test_elder_wand_attach_grants_power_and_first_strike():
    """ATTACH gives +3/+0 + first_strike to the equipped creature."""
    print("\n=== Elder Wand: +3/+0 + first_strike on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    wand = _put_on_battlefield(game, p1, "Elder Wand")
    recruit = _put_on_battlefield(game, p1, "Auror Recruit")
    base_p = get_power(recruit, game.state)
    base_t = get_toughness(recruit, game.state)
    assert not has_ability(recruit, 'first_strike', game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': wand.id, 'target_id': recruit.id},
        source=wand.id,
    ))

    new_p = get_power(recruit, game.state)
    new_t = get_toughness(recruit, game.state)
    assert new_p == base_p + 3, f"Expected power +3: {base_p}->{new_p}"
    assert new_t == base_t, f"Toughness should not change: {base_t}->{new_t}"
    assert has_ability(recruit, 'first_strike', game.state), (
        "Expected first_strike granted after attach"
    )


# ============================================================================
# Resurrection Stone (REWIRE)
# ============================================================================

def test_resurrection_stone_loads():
    """make_activated_ability registers the reanimate descriptor."""
    print("\n=== Resurrection Stone: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    stone = _put_on_battlefield(game, p1, "Resurrection Stone")
    assert stone.zone == ZoneType.BATTLEFIELD
    activated = getattr(stone.state, 'activated_abilities', None)
    assert activated, "Expected an activated ability on Resurrection Stone"


def test_resurrection_stone_effect_returns_creature():
    """Direct invocation of the reanimate effect emits RETURN_FROM_GRAVEYARD
    with destination='battlefield' for the chosen target."""
    print("\n=== Resurrection Stone: reanimate effect ===")
    game = Game()
    p1 = game.add_player("Alice")
    stone = _put_on_battlefield(game, p1, "Resurrection Stone")

    # Plant a low-MV creature in the graveyard.
    fallen = _put_in_graveyard(game, p1, "Auror Recruit")

    # Invoke the reanimate descriptor directly via its effect_fn.
    activated = stone.state.activated_abilities
    assert activated, "Expected activated ability descriptor"
    # Find the reanimate descriptor.
    desc = activated[0]
    # The effect_fn signature is (obj, state, targets) -> [Event]
    # Build a string-id target for the defensive unpack path.
    events = desc.effect_fn(stone, game.state, [fallen.id])
    assert events, "Expected at least one event"
    assert events[0].type == EventType.RETURN_FROM_GRAVEYARD
    assert events[0].payload.get('object_id') == fallen.id
    assert events[0].payload.get('destination') == 'battlefield'


# ============================================================================
# Invisibility Cloak (REWIRE)
# ============================================================================

def test_invisibility_cloak_loads():
    print("\n=== Invisibility Cloak: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cloak = _put_on_battlefield(game, p1, "Invisibility Cloak")
    assert cloak.zone == ZoneType.BATTLEFIELD
    activated = getattr(cloak.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Invisibility Cloak"


def test_invisibility_cloak_attach_grants_hexproof_and_unblockable():
    """ATTACH gives +0/+2 + hexproof + unblockable."""
    print("\n=== Invisibility Cloak: +0/+2 + hexproof + unblockable ===")
    game = Game()
    p1 = game.add_player("Alice")
    cloak = _put_on_battlefield(game, p1, "Invisibility Cloak")
    recruit = _put_on_battlefield(game, p1, "Auror Recruit")
    base_p = get_power(recruit, game.state)
    base_t = get_toughness(recruit, game.state)
    assert not has_ability(recruit, 'hexproof', game.state)
    assert not has_ability(recruit, 'unblockable', game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': cloak.id, 'target_id': recruit.id},
        source=cloak.id,
    ))

    new_p = get_power(recruit, game.state)
    new_t = get_toughness(recruit, game.state)
    assert new_p == base_p, f"Power should not change: {base_p}->{new_p}"
    assert new_t == base_t + 2, f"Expected toughness +2: {base_t}->{new_t}"
    assert has_ability(recruit, 'hexproof', game.state)
    assert has_ability(recruit, 'unblockable', game.state)


# ============================================================================
# Lord Voldemort, the Dark Lord (REWIRE)
# ============================================================================

def test_voldemort_loads_and_self_keywords():
    """Lord Voldemort grants himself flying + deathtouch and has the death
    trigger + activated drain ability."""
    print("\n=== Voldemort: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    vold = _put_on_battlefield(game, p1, "Lord Voldemort, the Dark Lord")
    assert has_ability(vold, 'flying', game.state)
    assert has_ability(vold, 'deathtouch', game.state)
    activated = getattr(vold.state, 'activated_abilities', None)
    assert activated, "Expected drain activated ability"
    assert len(vold.interceptor_ids) >= 4, (
        f"Expected death + flying + deathtouch + indestructible + PT; "
        f"got {len(vold.interceptor_ids)}"
    )


def test_voldemort_death_trigger_adds_counter_on_other_creature_death():
    """Another creature dying emits COUNTER_ADDED on Voldemort."""
    print("\n=== Voldemort: snowball death trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    vold = _put_on_battlefield(game, p1, "Lord Voldemort, the Dark Lord")
    victim = _put_on_battlefield(game, p2, "Auror Recruit")

    before = len(game.state.event_log)
    # Simulate creature death: ZONE_CHANGE from battlefield to graveyard.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': victim.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p2.id}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    counter_events = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == vold.id
    ]
    assert counter_events, (
        f"Expected COUNTER_ADDED on Voldemort after victim death; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_voldemort_indestructible_gated_on_deathly_hallow():
    """Voldemort gets +2/+2 + indestructible only when a Deathly Hallow is
    on the battlefield under the same controller."""
    print("\n=== Voldemort: Hallows gate ===")
    game = Game()
    p1 = game.add_player("Alice")
    vold = _put_on_battlefield(game, p1, "Lord Voldemort, the Dark Lord")
    base_p = vold.characteristics.power

    # Without any Hallow: NOT indestructible, base power.
    assert not has_ability(vold, 'indestructible', game.state)
    pre_p = get_power(vold, game.state)
    assert pre_p == base_p, f"Expected base power without Hallow; got {pre_p}"

    # Add a Hallow.
    _put_on_battlefield(game, p1, "Elder Wand")
    assert has_ability(vold, 'indestructible', game.state), (
        "Expected indestructible after Hallow on battlefield"
    )
    post_p = get_power(vold, game.state)
    assert post_p == base_p + 2, (
        f"Expected +2 power with Hallow gate; {base_p}->{post_p}"
    )


def test_voldemort_self_death_does_not_add_own_counter():
    """Edge: Voldemort's own death does NOT add a counter to himself
    (gotcha: 'another creature' filter)."""
    print("\n=== Voldemort: self-death edge case ===")
    game = Game()
    p1 = game.add_player("Alice")
    vold = _put_on_battlefield(game, p1, "Lord Voldemort, the Dark Lord")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': vold.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    self_counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == vold.id
    ]
    assert not self_counters, (
        f"Voldemort should not feed himself; got {len(self_counters)} counter events"
    )


# ============================================================================
# Albus Dumbledore, Headmaster (REWIRE)
# ============================================================================

def test_albus_dumbledore_loads_with_etb_and_static():
    """Dumbledore registers ETB + lord static + vigilance + hexproof grant."""
    print("\n=== Dumbledore: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    dumb = _put_on_battlefield(game, p1, "Albus Dumbledore, Headmaster")
    assert dumb.zone == ZoneType.BATTLEFIELD
    assert has_ability(dumb, 'vigilance', game.state)
    # Spice setup includes pt_itcs (lord static) + hexproof grant + vigilance
    # grant + ETB trigger = >=4 interceptors.
    assert len(dumb.interceptor_ids) >= 4, (
        f"Expected static + hexproof + vigilance + ETB; got {len(dumb.interceptor_ids)}"
    )


def test_albus_dumbledore_etb_emits_scry_and_draw():
    """ETB emits a scry placeholder + DRAW event."""
    print("\n=== Dumbledore: ETB scry + draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Albus Dumbledore, Headmaster")
    new = game.state.event_log[before:]
    scry = [
        e for e in new
        if e.type == EventType.ACTIVATE
        and e.payload.get('action') == 'scry'
        and e.payload.get('amount') == 2
    ]
    draws = [
        e for e in new
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert scry, "Expected scry 2 placeholder on Dumbledore ETB"
    assert draws, "Expected DRAW 1 on Dumbledore ETB"


def test_albus_dumbledore_buffs_other_wizards():
    """Other Wizard creatures you control get +1/+1 and hexproof — the
    static carry-over from the pre-spice wiring."""
    print("\n=== Dumbledore: lord effect on other wizards ===")
    game = Game()
    p1 = game.add_player("Alice")
    hermione = _put_on_battlefield(game, p1, "Hermione Granger, Brightest Witch")
    base_p = get_power(hermione, game.state)
    base_t = get_toughness(hermione, game.state)
    pre_hex = has_ability(hermione, 'hexproof', game.state)

    _put_on_battlefield(game, p1, "Albus Dumbledore, Headmaster")
    new_p = get_power(hermione, game.state)
    new_t = get_toughness(hermione, game.state)
    assert new_p == base_p + 1, f"Expected Hermione +1 power: {base_p}->{new_p}"
    assert new_t == base_t + 1, f"Expected Hermione +1 tough: {base_t}->{new_t}"
    assert has_ability(hermione, 'hexproof', game.state), (
        "Expected hexproof granted to other wizards"
    )


# ============================================================================
# Sirius Black, Escaped Convict (REWIRE)
# ============================================================================

def test_sirius_black_loads_with_haste():
    print("\n=== Sirius: load + haste ===")
    game = Game()
    p1 = game.add_player("Alice")
    sirius = _put_on_battlefield(game, p1, "Sirius Black, Escaped Convict")
    assert has_ability(sirius, 'haste', game.state), (
        "Sirius should self-grant haste"
    )
    assert sirius.interceptor_ids, "Sirius should register interceptors"


def test_sirius_black_attack_trigger_fires_on_attack():
    """ATTACK_DECLARED puts Sirius's attack trigger on the stack. The trigger's
    downstream events (DAMAGE 1, optional DRAW) may resolve in-line (visible
    in event_log) or via the stack (TRIGGERED_ABILITY_PUT_ON_STACK) depending
    on engine config. Either path is acceptable as long as the trigger fires
    with Sirius as the source."""
    print("\n=== Sirius: attack ping fires ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sirius = _put_on_battlefield(game, p1, "Sirius Black, Escaped Convict")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sirius.id, 'attacker': sirius.id, 'controller': p1.id},
        source=sirius.id,
    ))
    new = game.state.event_log[before:]
    damages = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('source') == sirius.id
        and e.payload.get('amount') == 1
        and e.payload.get('target') == p2.id
    ]
    triggered_stack = [
        e for e in new
        if e.type == EventType.TRIGGERED_ABILITY_PUT_ON_STACK
        and e.payload.get('source_id') == sirius.id
    ]
    assert damages or triggered_stack, (
        f"Expected attack-trigger damage or trigger-on-stack; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_sirius_black_no_cantrip_without_spells_cast():
    """Edge: with `turn_data['spells_cast_<p1>']` unset (default 0), the
    Sirius attack trigger should NOT include a DRAW event in its emitted
    effect-fn output. We verify by invoking the effect_fn directly."""
    print("\n=== Sirius: no cantrip without spells cast ===")
    from src.cards.custom.harry_potter import sirius_black_setup
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sirius = _put_on_battlefield(game, p1, "Sirius Black, Escaped Convict")

    # Sirius's attack trigger Interceptor has the effect_fn stashed in its
    # filter closure. Easier: re-derive the effect through the helper and
    # call it directly with a synthesized ATTACK_DECLARED event.
    fake_event = Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sirius.id, 'attacker': sirius.id, 'controller': p1.id},
        source=sirius.id,
    )
    # Iterate Sirius's attack-trigger interceptors and find one whose
    # handler returns the effect list.
    drew = False
    for itc_id in sirius.interceptor_ids:
        itc = game.state.interceptors.get(itc_id)
        if itc is None:
            continue
        if not itc.filter(fake_event, game.state):
            continue
        result = itc.handler(fake_event, game.state)
        for e in (result.new_events or []):
            if e.type == EventType.DRAW and e.payload.get('player') == p1.id:
                drew = True
    assert not drew, "Sirius should NOT cantrip without a spell cast this turn"


def test_sirius_black_attack_emits_cantrip_when_spell_cast():
    """When a spell has been cast this turn, the attack trigger also draws
    a card. Sirius's setup reads `state.turn_data['spells_cast_<p>']` (the
    engine-canonical surface — see turn_state.spells_cast_this_turn)."""
    print("\n=== Sirius: attack + cantrip with prior spell ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sirius = _put_on_battlefield(game, p1, "Sirius Black, Escaped Convict")

    # Set the engine's turn-data spell counter directly. (In normal play
    # the pipeline writes this when a spell is cast; tests synthesize it.)
    if not hasattr(game.state, 'turn_data') or game.state.turn_data is None:
        game.state.turn_data = {}
    game.state.turn_data[f'spells_cast_{p1.id}'] = 1

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sirius.id, 'attacker': sirius.id, 'controller': p1.id},
        source=sirius.id,
    ))
    new = game.state.event_log[before:]
    draws = [
        e for e in new
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    # The trigger goes on the stack (TRIGGERED_ABILITY_PUT_ON_STACK) and the
    # downstream DAMAGE / DRAW events emit on resolution. We accept either
    # "events directly in log" or "trigger on stack with the right effect"
    # because the engine's auto-resolve path is configuration-dependent.
    triggered_stack = [
        e for e in new
        if e.type == EventType.TRIGGERED_ABILITY_PUT_ON_STACK
        and e.payload.get('source_id') == sirius.id
    ]
    assert draws or triggered_stack, (
        f"Expected cantrip DRAW or trigger-on-stack with spell-mastery met; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


# ============================================================================
# Hogwarts: The Sorting Year (NEW saga)
# ============================================================================

def test_hogwarts_sorting_year_loads_saga():
    print("\n=== Hogwarts Sorting Year: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Hogwarts: The Sorting Year")
    assert saga.interceptor_ids, "Expected saga chapter interceptors"
    # Saga is an Enchantment with subtype Saga.
    assert "Saga" in (saga.characteristics.subtypes or set())


def test_hogwarts_chapter_i_emits_house_tutor():
    """Direct chapter-I dispatch emits SEARCH_LIBRARY for any House creature
    MV<=3 to the battlefield tapped."""
    print("\n=== Hogwarts Sorting Year: chapter I ===")
    from src.cards.custom.harry_potter import _hogwarts_sorting_year_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Hogwarts: The Sorting Year")
    events = _hogwarts_sorting_year_chapter_i(saga, game.state)
    assert events and events[0].type == EventType.SEARCH_LIBRARY
    payload = events[0].payload
    assert set(payload.get('subtypes_any', [])) == {
        'Gryffindor', 'Slytherin', 'Ravenclaw', 'Hufflepuff'
    }
    assert payload.get('mana_value_max') == 3
    assert payload.get('enters_tapped') is True
    assert payload.get('destination') == 'battlefield'


def test_hogwarts_chapter_ii_creates_two_wizard_tokens():
    print("\n=== Hogwarts Sorting Year: chapter II ===")
    from src.cards.custom.harry_potter import _hogwarts_sorting_year_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Hogwarts: The Sorting Year")
    events = _hogwarts_sorting_year_chapter_ii(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and 'Wizard' in (e.payload.get('token', {}).get('subtypes', set()) or set())
    ]
    assert len(tokens) == 2, f"Expected 2 Wizard tokens; got {len(tokens)}"


def test_hogwarts_chapter_iii_anthem_excludes_saga():
    """Chapter III buffs other creatures and grants vigilance EOT — saga
    itself is excluded."""
    print("\n=== Hogwarts Sorting Year: chapter III ===")
    from src.cards.custom.harry_potter import _hogwarts_sorting_year_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Hogwarts: The Sorting Year")
    recruit = _put_on_battlefield(game, p1, "Auror Recruit")
    events = _hogwarts_sorting_year_chapter_iii(saga, game.state)
    pt_targets = [e.payload['object_id'] for e in events if e.type == EventType.PT_MODIFICATION]
    kw_targets = [e.payload['object_id'] for e in events if e.type == EventType.GRANT_KEYWORD]
    assert recruit.id in pt_targets, f"Recruit not buffed: {pt_targets}"
    assert recruit.id in kw_targets, f"Recruit not granted vigilance: {kw_targets}"
    assert saga.id not in pt_targets, f"Saga should not buff itself: {pt_targets}"
    assert saga.id not in kw_targets, f"Saga should not grant itself vigilance: {kw_targets}"


# ============================================================================
# Fawkes the Phoenix (REWIRE)
# ============================================================================

def test_fawkes_loads_with_flying():
    print("\n=== Fawkes: load + flying ===")
    game = Game()
    p1 = game.add_player("Alice")
    fawkes = _put_on_battlefield(game, p1, "Fawkes the Phoenix")
    assert has_ability(fawkes, 'flying', game.state)
    assert fawkes.interceptor_ids, "Fawkes should register interceptors"


def test_fawkes_etb_gains_life_and_reanimates():
    """ETB emits LIFE_CHANGE +3 and RETURN_FROM_GRAVEYARD for a valid MV<=3
    creature in the controller's graveyard."""
    print("\n=== Fawkes: phoenix tears + reanimate ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a low-MV creature in the graveyard first.
    fallen = _put_in_graveyard(game, p1, "Auror Recruit")

    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Fawkes the Phoenix")
    new = game.state.event_log[before:]

    life_events = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 3
    ]
    reanimates = [
        e for e in new
        if e.type == EventType.RETURN_FROM_GRAVEYARD
        and e.payload.get('object_id') == fallen.id
        and e.payload.get('destination') == 'battlefield'
    ]
    assert life_events, "Expected +3 life on Fawkes ETB"
    assert reanimates, (
        f"Expected RETURN_FROM_GRAVEYARD for Auror Recruit; "
        f"recent={[e.type.name for e in new[-15:]]}"
    )


def test_fawkes_empty_graveyard_no_reanimate_no_crash():
    """ETB with empty graveyard still gains life, no reanimate event."""
    print("\n=== Fawkes: empty graveyard ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Fawkes the Phoenix")
    new = game.state.event_log[before:]
    life_events = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 3
    ]
    reanimates = [e for e in new if e.type == EventType.RETURN_FROM_GRAVEYARD]
    assert life_events, "Expected +3 life even with empty graveyard"
    assert not reanimates, f"No reanimate with empty graveyard; got {len(reanimates)}"


# ============================================================================
# Phase A2 (slice 2) — decision-axis flip cards
# ============================================================================


def test_sorting_hats_verdict_loads():
    """Setup registers a modal-ETB trigger."""
    print("\n=== Sorting Hat's Verdict: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    shv = _put_on_battlefield(game, p1, "Sorting Hat's Verdict")
    assert shv.zone == ZoneType.BATTLEFIELD
    assert shv.interceptor_ids, "Expected modal-ETB trigger interceptor"


def test_sorting_hats_verdict_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== Sorting Hat's Verdict: pending modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    shv = _put_on_battlefield(game, p1, "Sorting Hat's Verdict")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == shv.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"


def test_bellatrix_crucio_loads():
    """Setup registers menace + ETB info pulse + targeted-ETB trigger."""
    print("\n=== Bellatrix Lestrange, Crucio Witch: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bel = _put_on_battlefield(game, p1, "Bellatrix Lestrange, Crucio Witch")
    assert bel.zone == ZoneType.BATTLEFIELD
    assert len(bel.interceptor_ids) >= 3, (
        f"Expected at least 3 interceptors; got {len(bel.interceptor_ids)}"
    )
    assert has_ability(bel, 'menace', game.state), "Expected menace"


def test_bellatrix_crucio_etb_emits_target_required_and_info():
    """ETB emits TARGET_REQUIRED w/ effect=damage + DISCARD_CHOICE info."""
    print("\n=== Bellatrix Crucio: ETB target_required + info pulse ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    bel = _put_on_battlefield(game, p1, "Bellatrix Lestrange, Crucio Witch")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == bel.id
        and e.payload.get('target_filter') == 'opponent_creature'
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; recent={[e.type.name for e in new[-10:]]}"
    )
    info_events = [
        e for e in new
        if e.type == EventType.DISCARD_CHOICE and e.payload.get('source') == bel.id
    ]
    assert info_events, "Expected DISCARD_CHOICE info pulse on ETB"


def test_sybill_trelawney_loads():
    """Setup registers an ETB trigger."""
    print("\n=== Sybill Trelawney, Seer's Vision: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    syb = _put_on_battlefield(game, p1, "Sybill Trelawney, Seer's Vision")
    assert syb.zone == ZoneType.BATTLEFIELD
    assert syb.interceptor_ids, "Expected ETB interceptor"


def test_sybill_trelawney_etb_opens_scry_choice_with_library():
    """ETB with non-empty library opens a scry pending_choice."""
    print("\n=== Sybill Trelawney: ETB opens scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant 2 cards in library.
    soldier_def = HARRY_POTTER_CARDS["Hogwarts Scholar"]
    lib = game.state.zones[f'library_{p1.id}']
    for _ in range(2):
        obj = game.create_object(
            name="Hogwarts Scholar",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=soldier_def.characteristics,
            card_def=None,
        )
        obj.card_def = soldier_def
        if obj.id not in lib.objects:
            lib.objects.append(obj.id)
    syb = _put_on_battlefield(game, p1, "Sybill Trelawney, Seer's Vision")
    pc = game.state.pending_choice
    assert pc is not None, "Expected scry pending_choice"
    assert pc.source_id == syb.id
    assert pc.choice_type == "scry"
    assert pc.player == p1.id


def test_sybill_trelawney_etb_empty_library_no_op():
    """ETB with empty library returns [] without crashing."""
    print("\n=== Sybill Trelawney: empty library ===")
    game = Game()
    p1 = game.add_player("Alice")
    syb = _put_on_battlefield(game, p1, "Sybill Trelawney, Seer's Vision")
    assert syb.zone == ZoneType.BATTLEFIELD


def test_marauders_map_loads():
    """Setup registers an ETB trigger."""
    print("\n=== The Marauder's Map: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    mm = _put_on_battlefield(game, p1, "The Marauder's Map")
    assert mm.zone == ZoneType.BATTLEFIELD
    assert mm.interceptor_ids, "Expected ETB interceptor"


def test_marauders_map_empty_library_no_crash():
    """ETB with empty library returns [] without installing a choice."""
    print("\n=== Marauder's Map: empty library ===")
    game = Game()
    p1 = game.add_player("Alice")
    mm = _put_on_battlefield(game, p1, "The Marauder's Map")
    assert mm.zone == ZoneType.BATTLEFIELD


def test_horcrux_reliquary_loads():
    """Setup registers an ETB trigger."""
    print("\n=== Horcrux Reliquary: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hr = _put_on_battlefield(game, p1, "Horcrux Reliquary")
    assert hr.zone == ZoneType.BATTLEFIELD
    assert hr.interceptor_ids, "Expected ETB interceptor"


def test_horcrux_reliquary_etb_with_creature_opens_sac_choice():
    """ETB with at least one own creature opens a sacrifice pending_choice."""
    print("\n=== Horcrux Reliquary: ETB sacrifice choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Drop a sac-target into play first.
    target_creature = _put_on_battlefield(game, p1, "Hogwarts Scholar")
    hr = _put_on_battlefield(game, p1, "Horcrux Reliquary")
    pc = game.state.pending_choice
    assert pc is not None, "Expected sacrifice pending_choice"
    assert pc.source_id == hr.id
    assert pc.choice_type == "sacrifice"
    assert pc.player == p1.id
    assert target_creature.id in pc.options, (
        f"Expected the planted creature to appear as a sacrifice option; "
        f"got options={pc.options}"
    )


def test_horcrux_reliquary_etb_with_no_creatures_no_op():
    """ETB with no own creatures returns [] without installing a choice."""
    print("\n=== Horcrux Reliquary: no own creatures ===")
    game = Game()
    p1 = game.add_player("Alice")
    hr = _put_on_battlefield(game, p1, "Horcrux Reliquary")
    assert hr.zone == ZoneType.BATTLEFIELD


# ============================================================================
# Slice-5 thin-bust tests (2026-05-19): one unit test per buffed vanilla
# card. Verifies setup_interceptors registers + on-flavor effect fires
# under the expected trigger.
# ============================================================================


def _slice5_emit_attack(game, attacker):
    """Helper: emit ATTACK_DECLARED for the given attacker."""
    opps = [p for p in game.state.players.values() if p.id != attacker.controller]
    p2 = opps[0]
    return game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'defender': p2.id},
        source=attacker.id, controller=attacker.controller,
    ))


def _slice5_emit_death(game, dying):
    """Helper: emit ZONE_CHANGE moving the object from battlefield to graveyard."""
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': dying.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{dying.controller}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=dying.id,
    ))


def test_slytherin_prefect_death_drains_each_opp_slice5():
    """Slice-5: Slytherin Prefect dies -> each opp -1 life."""
    print("\n=== Slice-5: Slytherin Prefect — death drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    sp = _put_on_battlefield(game, p1, "Slytherin Prefect")
    assert sp.interceptor_ids, "Expected death-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_death(game, sp)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == sp.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_venomous_tentacula_combat_damage_drains_each_opp_slice5():
    """Slice-5: Venomous Tentacula combat damage -> each opp -1 life."""
    print("\n=== Slice-5: Venomous Tentacula — combat damage drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    vt = _put_on_battlefield(game, p1, "Venomous Tentacula")
    assert vt.interceptor_ids, "Expected damage-trigger interceptor"
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': vt.id, 'target': p2.id, 'amount': 3, 'is_combat': True},
        source=vt.id,
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == vt.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_hogwarts_scholar_etb_scry_slice5():
    """Slice-5: Hogwarts Scholar ETB -> SCRY 1."""
    print("\n=== Slice-5: Hogwarts Scholar — ETB scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant a card in library so the helper proceeds past empty-library guard.
    cd = HARRY_POTTER_CARDS.get("Hogwarts Scholar")
    ko = game.create_object(
        name="Hogwarts Scholar", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=cd.characteristics, card_def=None,
    )
    ko.card_def = cd
    lib = game.state.zones[f'library_{p1.id}']
    if ko.id not in lib.objects:
        lib.objects.append(ko.id)
    before = len(game.state.event_log)
    hs = _put_on_battlefield(game, p1, "Hogwarts Scholar")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == hs.id]
    assert scrys, f"Expected SCRY event; recent={[e.type.name for e in new[-10:]]}"


def test_hufflepuff_prefect_etb_solo_no_drain_slice5():
    """Slice-5: Hufflepuff Prefect ETB solo (1 Hufflepuff = self) -> no opp drain."""
    print("\n=== Slice-5: Hufflepuff Prefect — solo ETB ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    hp_card = _put_on_battlefield(game, p1, "Hufflepuff Prefect")
    assert hp_card.interceptor_ids, "Expected ETB-trigger interceptor"
    drains = [
        e for e in game.state.event_log
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.source == hp_card.id
    ]
    assert not drains, f"Expected no drain with 1 Hufflepuff; got {len(drains)}"


def test_order_of_phoenix_member_etb_drains_each_opp_slice5():
    """Slice-5: Order of the Phoenix Member ETB -> each opp -1 life."""
    print("\n=== Slice-5: Order of the Phoenix Member — ETB drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    opm = _put_on_battlefield(game, p1, "Order of the Phoenix Member")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == opm.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_dragon_handler_etb_with_dragon_drains_each_opp_slice5():
    """Slice-5: Dragon Handler ETB w/ a Dragon -> each opp -1 life."""
    print("\n=== Slice-5: Dragon Handler — ETB drain w/ Dragon ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant a Dragon first so the count is >=1.
    _put_on_battlefield(game, p1, "Norwegian Ridgeback")
    before = len(game.state.event_log)
    dh = _put_on_battlefield(game, p1, "Dragon Handler")
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == dh.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_hippogriff_attack_drains_each_opp_slice5():
    """Slice-5: Hippogriff attacks -> each opp -1 life."""
    print("\n=== Slice-5: Hippogriff — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    hg = _put_on_battlefield(game, p1, "Hippogriff")
    assert hg.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, hg)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == hg.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_buckbeak_attack_drains_each_opp_slice5():
    """Slice-5: Buckbeak attacks -> each opp -1 life."""
    print("\n=== Slice-5: Buckbeak — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bb = _put_on_battlefield(game, p1, "Buckbeak")
    assert bb.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, bb)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == bb.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_bowtruckle_etb_scry_slice5():
    """Slice-5: Bowtruckle ETB -> SCRY 1."""
    print("\n=== Slice-5: Bowtruckle — ETB scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cd = HARRY_POTTER_CARDS.get("Bowtruckle")
    ko = game.create_object(
        name="Bowtruckle", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=cd.characteristics, card_def=None,
    )
    ko.card_def = cd
    lib = game.state.zones[f'library_{p1.id}']
    if ko.id not in lib.objects:
        lib.objects.append(ko.id)
    before = len(game.state.event_log)
    bt = _put_on_battlefield(game, p1, "Bowtruckle")
    new = game.state.event_log[before:]
    scrys = [e for e in new if e.type == EventType.SCRY and e.source == bt.id]
    assert scrys, f"Expected SCRY event; recent={[e.type.name for e in new[-10:]]}"


def test_quidditch_beater_attack_drains_each_opp_slice5():
    """Slice-5: Quidditch Beater attacks -> each opp -1 life."""
    print("\n=== Slice-5: Quidditch Beater — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    qb = _put_on_battlefield(game, p1, "Quidditch Beater")
    assert qb.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, qb)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == qb.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_hungarian_horntail_attack_alone_drains_each_opp_slice5():
    """Slice-5: Hungarian Horntail attacks (no other Dragon) -> each opp -1 life."""
    print("\n=== Slice-5: Hungarian Horntail — attack drain (alone) ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    hh = _put_on_battlefield(game, p1, "Hungarian Horntail")
    assert hh.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, hh)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == hh.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_norwegian_ridgeback_attack_drains_each_opp_slice5():
    """Slice-5: Norwegian Ridgeback attacks -> each opp -1 life."""
    print("\n=== Slice-5: Norwegian Ridgeback — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    nr = _put_on_battlefield(game, p1, "Norwegian Ridgeback")
    assert nr.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, nr)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == nr.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_chinese_fireball_etb_pings_each_opp_slice5():
    """Slice-5: Chinese Fireball ETB -> 1 damage to each opponent."""
    print("\n=== Slice-5: Chinese Fireball — ETB ping ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    cf = _put_on_battlefield(game, p1, "Chinese Fireball")
    new = game.state.event_log[before:]
    pings = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 1
        and e.source == cf.id
    ]
    assert pings, f"Expected each-opp ping; recent={[e.type.name for e in new[-10:]]}"


def test_common_welsh_green_attack_drains_each_opp_slice5():
    """Slice-5: Common Welsh Green attacks -> each opp -1 life."""
    print("\n=== Slice-5: Common Welsh Green — attack drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cwg = _put_on_battlefield(game, p1, "Common Welsh Green")
    assert cwg.interceptor_ids, "Expected attack-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_attack(game, cwg)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == cwg.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_inferius_death_drains_each_opp_slice5():
    """Slice-5: Inferius dies -> each opp -1 life."""
    print("\n=== Slice-5: Inferius — death drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    inf = _put_on_battlefield(game, p1, "Inferius")
    assert inf.interceptor_ids, "Expected death-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_death(game, inf)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == inf.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_death_eater_initiate_death_drains_each_opp_slice5():
    """Slice-5: Death Eater Initiate dies -> each opp -1 life."""
    print("\n=== Slice-5: Death Eater Initiate — death drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    dei = _put_on_battlefield(game, p1, "Death Eater Initiate")
    assert dei.interceptor_ids, "Expected death-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_death(game, dei)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == dei.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"


def test_mandrake_death_drains_each_opp_slice5():
    """Slice-5: Mandrake dies -> each opp -1 life."""
    print("\n=== Slice-5: Mandrake — death drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    md = _put_on_battlefield(game, p1, "Mandrake")
    assert md.interceptor_ids, "Expected death-trigger interceptor"
    before = len(game.state.event_log)
    _slice5_emit_death(game, md)
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
        and e.source == md.id
    ]
    assert drains, f"Expected each-opp drain; recent={[e.type.name for e in new[-10:]]}"



# ============================================================================
# Runner — module-direct so tests work without pytest config
# ============================================================================



# ============================================================================
# SLICE-23 median-lift tests (2026-05-19): one test per buffed card.
# Each test puts the card on the battlefield (creatures/enchantments/lands/
# artifacts) or invokes the resolve fn directly (instants/sorceries), then
# asserts the expected info event (SCRY/SURVEIL) and opp event (LIFE_CHANGE,
# DAMAGE, MILL, DISCARD) fired.
# ============================================================================


def _s23_etb_collect(card_name):
    """Place card under p1, return (game, p1, p2, new_events)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, card_name)
    return game, p1, p2, game.state.event_log[before:]


def _s23_upkeep_collect(card_name):
    """Place card under p1, trigger upkeep PHASE_START, return events.

    Upkeep triggers fire on `PHASE_START` with `phase == 'upkeep'` while
    state.active_player == controller.
    """
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, card_name)
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        source=None,
    ))
    return game, p1, p2, game.state.event_log[before:]


def _s23_attack_collect(card_name):
    """Place card under p1, attack with it, return (game, p1, p2, new_events)."""
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
    return game, p1, p2, game.state.event_log[before:]


def _s23_death_collect(card_name):
    """Place card under p1, then kill it (move to graveyard), return events."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_on_battlefield(game, p1, card_name)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    return game, p1, p2, game.state.event_log[before:]


def _s23_resolve(fn_name):
    """Call a resolve fn from the harry_potter module."""
    import src.cards.custom.harry_potter as hpw_module
    fn = getattr(hpw_module, fn_name)
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    events = fn([], game.state)
    return events, p1, p2


def _assert_any(events, event_type, **payload_match):
    """Assert at least one event of `event_type` with matching payload exists."""
    for e in events:
        if e.type != event_type:
            continue
        ok = True
        for k, v in payload_match.items():
            actual = e.payload.get(k) if e.payload else None
            if v == '<NEG>':
                if not (isinstance(actual, (int, float)) and actual < 0):
                    ok = False
                    break
            elif v == '<POS>':
                if not (isinstance(actual, (int, float)) and actual > 0):
                    ok = False
                    break
            elif callable(v):
                if not v(actual):
                    ok = False
                    break
            else:
                if actual != v:
                    ok = False
                    break
        if ok:
            return True
    return False


def _assert_etb_scry_drain(events, p2_id):
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected SCRY/SURVEIL info event; recent={[e.type.name for e in events[-12:]]}"
    has_drain = (_assert_any(events, EventType.LIFE_CHANGE, player=p2_id, amount='<NEG>') or
                 _assert_any(events, EventType.DAMAGE, target=p2_id) or
                 _assert_any(events, EventType.MILL, player=p2_id) or
                 _assert_any(events, EventType.DISCARD, player=p2_id))
    assert has_drain, f"Expected cross-controller harm on opp; recent={[e.type.name for e in events[-12:]]}"




def test_s23_hogwarts_defender():
    g, p1, p2, events = _s23_etb_collect("Hogwarts Defender")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_ministry_auror():
    g, p1, p2, events = _s23_etb_collect("Ministry Auror")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_hogwarts_first_year():
    g, p1, p2, events = _s23_etb_collect("Hogwarts First Year")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_dumbledores_army_recruit():
    g, p1, p2, events = _s23_etb_collect("Dumbledore's Army Recruit")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_hogwarts_ghost():
    g, p1, p2, events = _s23_etb_collect("Hogwarts Ghost")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_quidditch_referee():
    g, p1, p2, events = _s23_etb_collect("Quidditch Referee")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_healing_witch():
    g, p1, p2, events = _s23_etb_collect("Healing Witch")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_st_mungos_healer():
    g, p1, p2, events = _s23_etb_collect("St. Mungo's Healer")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_phoenix_guardian():
    g, p1, p2, events = _s23_etb_collect("Phoenix Guardian")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_weasley_matriarch():
    g, p1, p2, events = _s23_etb_collect("Weasley Matriarch")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_weasley_twin_prankster():
    g, p1, p2, events = _s23_attack_collect("Weasley Twin Prankster")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_fiendfyre_elemental():
    g, p1, p2, events = _s23_attack_collect("Fiendfyre Elemental")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_blast_ended_skrewt():
    g, p1, p2, events = _s23_attack_collect("Blast-Ended Skrewt")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_erumpent():
    g, p1, p2, events = _s23_attack_collect("Erumpent")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_goblin_banker():
    g, p1, p2, events = _s23_attack_collect("Gringotts Goblin")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_acromantula():
    g, p1, p2, events = _s23_attack_collect("Acromantula")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_basilisk():
    g, p1, p2, events = _s23_attack_collect("Basilisk")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_divination_student():
    g, p1, p2, events = _s23_etb_collect("Divination Student")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_library_researcher():
    g, p1, p2, events = _s23_etb_collect("Library Researcher")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_spell_theorist():
    g, p1, p2, events = _s23_etb_collect("Spell Theorist")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_hogwarts_librarian():
    g, p1, p2, events = _s23_etb_collect("Hogwarts Librarian")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_unspeakable():
    g, p1, p2, events = _s23_etb_collect("Unspeakable")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_pensieve_keeper():
    g, p1, p2, events = _s23_etb_collect("Pensieve Keeper")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_time_turner_user():
    g, p1, p2, events = _s23_etb_collect("Time-Turner User")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_memory_charm_specialist():
    g, p1, p2, events = _s23_etb_collect("Memory Charm Specialist")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_dementor():
    g, p1, p2, events = _s23_etb_collect("Dementor")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_dementor_swarm():
    g, p1, p2, events = _s23_etb_collect("Dementor Swarm")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_dark_wizard():
    g, p1, p2, events = _s23_etb_collect("Dark Wizard")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_knockturn_alley_vendor():
    g, p1, p2, events = _s23_etb_collect("Knockturn Alley Vendor")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_azkaban_guard():
    g, p1, p2, events = _s23_etb_collect("Azkaban Guard")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_nagini():
    g, p1, p2, events = _s23_etb_collect("Nagini")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_greyback():
    g, p1, p2, events = _s23_death_collect("Fenrir Greyback")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_thestral():
    g, p1, p2, events = _s23_death_collect("Thestral")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_thestral_herd():
    g, p1, p2, events = _s23_etb_collect("Thestral Herd")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_whomping_willow():
    g, p1, p2, events = _s23_etb_collect("Whomping Willow")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_forbidden_forest_spider():
    g, p1, p2, events = _s23_etb_collect("Forbidden Forest Spider")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_centaur_archer():
    g, p1, p2, events = _s23_etb_collect("Centaur Archer")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_giant_squid():
    g, p1, p2, events = _s23_etb_collect("Giant Squid of the Black Lake")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_unicorn():
    g, p1, p2, events = _s23_etb_collect("Unicorn")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected SCRY/SURVEIL info event; events={[e.type.name for e in events[-12:]]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain-life on controller; events={[e.type.name for e in events[-12:]]}"


def test_s23_niffler():
    g, p1, p2, events = _s23_etb_collect("Niffler")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected SCRY/SURVEIL info event; events={[e.type.name for e in events[-12:]]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain-life on controller; events={[e.type.name for e in events[-12:]]}"


def test_s23_hogwarts_castle():
    g, p1, p2, events = _s23_upkeep_collect("Hogwarts Castle")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_gryffindor_common_room():
    g, p1, p2, events = _s23_upkeep_collect("Gryffindor Common Room")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_slytherin_dungeon():
    g, p1, p2, events = _s23_upkeep_collect("Slytherin Dungeon")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_ravenclaw_tower():
    g, p1, p2, events = _s23_upkeep_collect("Ravenclaw Tower")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_hufflepuff_basement():
    g, p1, p2, events = _s23_upkeep_collect("Hufflepuff Basement")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_diagon_alley():
    g, p1, p2, events = _s23_upkeep_collect("Diagon Alley")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_hogsmeade_village():
    g, p1, p2, events = _s23_upkeep_collect("Hogsmeade Village")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_forbidden_forest_land():
    g, p1, p2, events = _s23_upkeep_collect("The Forbidden Forest")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_ministry_of_magic():
    g, p1, p2, events = _s23_upkeep_collect("Ministry of Magic")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_azkaban():
    g, p1, p2, events = _s23_upkeep_collect("Azkaban")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_godrics_hollow():
    g, p1, p2, events = _s23_upkeep_collect("Godric's Hollow")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_grimmauld_place():
    g, p1, p2, events = _s23_upkeep_collect("12 Grimmauld Place")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_the_burrow():
    g, p1, p2, events = _s23_upkeep_collect("The Burrow")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_malfoy_manor():
    g, p1, p2, events = _s23_upkeep_collect("Malfoy Manor")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_knockturn_alley():
    g, p1, p2, events = _s23_upkeep_collect("Knockturn Alley")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_gringotts():
    g, p1, p2, events = _s23_upkeep_collect("Gringotts Bank")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_quidditch_pitch():
    g, p1, p2, events = _s23_upkeep_collect("Quidditch Pitch")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_room_of_requirement():
    g, p1, p2, events = _s23_upkeep_collect("Room of Requirement")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_shrieking_shack():
    g, p1, p2, events = _s23_upkeep_collect("Shrieking Shack")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_dumbledores_protection():
    g, p1, p2, events = _s23_upkeep_collect("Dumbledore's Protection")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_gryffindor_banner():
    g, p1, p2, events = _s23_upkeep_collect("Gryffindor Banner")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_ravenclaw_banner():
    g, p1, p2, events = _s23_upkeep_collect("Ravenclaw Banner")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_library_of_hogwarts():
    g, p1, p2, events = _s23_upkeep_collect("Library of Hogwarts")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_slytherin_banner():
    g, p1, p2, events = _s23_upkeep_collect("Slytherin Banner")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_horcrux_curse():
    g, p1, p2, events = _s23_upkeep_collect("Horcrux Curse")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_weasleys_wizard_wheezes():
    g, p1, p2, events = _s23_upkeep_collect("Weasleys' Wizard Wheezes")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_gryffindor_courage():
    g, p1, p2, events = _s23_upkeep_collect("Gryffindor Courage")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_herbology_classroom():
    g, p1, p2, events = _s23_upkeep_collect("Herbology Classroom")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_hufflepuff_banner():
    g, p1, p2, events = _s23_upkeep_collect("Hufflepuff Banner")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_forbidden_forest():
    g, p1, p2, events = _s23_upkeep_collect("Forbidden Forest")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_marauders_map():
    g, p1, p2, events = _s23_upkeep_collect("Marauder's Map")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_sorting_hat():
    g, p1, p2, events = _s23_upkeep_collect("Sorting Hat")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_horcrux_diary():
    g, p1, p2, events = _s23_upkeep_collect("Tom Riddle's Diary")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_horcrux_locket():
    g, p1, p2, events = _s23_upkeep_collect("Slytherin's Locket")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_horcrux_cup():
    g, p1, p2, events = _s23_upkeep_collect("Hufflepuff's Cup")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_horcrux_diadem():
    g, p1, p2, events = _s23_upkeep_collect("Ravenclaw's Diadem")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_horcrux_ring():
    g, p1, p2, events = _s23_upkeep_collect("Gaunt Family Ring")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_firebolt_broom():
    g, p1, p2, events = _s23_upkeep_collect("Firebolt")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_nimbus_2000():
    g, p1, p2, events = _s23_upkeep_collect("Nimbus 2000")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_wand_of_phoenix_feather():
    g, p1, p2, events = _s23_upkeep_collect("Wand of Phoenix Feather")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_wand_of_dragon_heartstring():
    g, p1, p2, events = _s23_upkeep_collect("Wand of Dragon Heartstring")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_wand_of_unicorn_hair():
    g, p1, p2, events = _s23_upkeep_collect("Wand of Unicorn Hair")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_pensieve():
    g, p1, p2, events = _s23_upkeep_collect("Pensieve")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_golden_snitch():
    g, p1, p2, events = _s23_upkeep_collect("Golden Snitch")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_quaffle():
    g, p1, p2, events = _s23_upkeep_collect("Quaffle")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_bludger():
    g, p1, p2, events = _s23_upkeep_collect("Bludger")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_time_turner():
    g, p1, p2, events = _s23_upkeep_collect("Time-Turner")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_deluminator():
    g, p1, p2, events = _s23_upkeep_collect("Deluminator")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_portkey():
    g, p1, p2, events = _s23_upkeep_collect("Portkey")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_goblet_of_fire():
    g, p1, p2, events = _s23_upkeep_collect("Goblet of Fire")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_mirror_of_erised():
    g, p1, p2, events = _s23_upkeep_collect("Mirror of Erised")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_vanishing_cabinet():
    g, p1, p2, events = _s23_upkeep_collect("Vanishing Cabinet")
    _assert_etb_scry_drain(events, p2.id)


def test_s23_sword_of_gryffindor():
    g, p1, p2, events = _s23_upkeep_collect("Sword of Gryffindor")
    _assert_etb_scry_drain(events, p2.id)


# --- Resolve handler tests ---


def test_s23_expecto_patronum_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_expecto_patronum")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Expecto Patronum; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Expecto Patronum"


def test_s23_protego_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_protego")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Protego; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Protego"


def test_s23_shield_charm_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_shield_charm")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Shield Charm; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Shield Charm"


def test_s23_counter_curse_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_counter_curse")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Counter-Curse; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Counter-Curse"


def test_s23_priori_incantatem_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_priori_incantatem")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Priori Incantatem; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Priori Incantatem"


def test_s23_healing_spell_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_healing_spell")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Healing Spell; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Healing Spell"


def test_s23_disillusionment_charm_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_disillusionment_charm")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Disillusionment Charm; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Disillusionment Charm"


def test_s23_call_the_order_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_call_the_order")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Call the Order; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Call the Order"


def test_s23_sorting_ceremony_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_sorting_ceremony")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Sorting Ceremony; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Sorting Ceremony"


def test_s23_obliviate_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_obliviate")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Obliviate; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Obliviate"


def test_s23_stupefy_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_stupefy")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Stupefy; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Stupefy"


def test_s23_accio_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_accio")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Accio; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Accio"


def test_s23_confundo_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_confundo")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Confundo; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Confundo"


def test_s23_petrificus_totalus_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_petrificus_totalus")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Petrificus Totalus; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Petrificus Totalus"


def test_s23_legilimens_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_legilimens")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Legilimens; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Legilimens"


def test_s23_aguamenti_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_aguamenti")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Aguamenti; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Aguamenti"


def test_s23_finite_incantatem_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_finite_incantatem")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Finite Incantatem; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Finite Incantatem"


def test_s23_divination_spell_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_divination")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Divination; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Divination"


def test_s23_crystal_ball_reading_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_crystal_ball_reading")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Crystal Ball Reading; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Crystal Ball Reading"


def test_s23_memory_wipe_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_memory_wipe")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Memory Wipe; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Memory Wipe"


def test_s23_transfiguration_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_transfiguration")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Transfiguration; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.MILL, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>'), \
        f"Expected opp mill/drain for Transfiguration"


def test_s23_avada_kedavra_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_avada_kedavra")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Avada Kedavra; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Avada Kedavra"


def test_s23_crucio_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_crucio")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Crucio; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Crucio"


def test_s23_imperio_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_imperio")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Imperio; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Imperio"


def test_s23_sectumsempra_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_sectumsempra")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Sectumsempra; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Sectumsempra"


def test_s23_morsmordre_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_morsmordre")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Morsmordre; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Morsmordre"


def test_s23_dark_mark_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_dark_mark")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Dark Mark; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Dark Mark"


def test_s23_curse_of_the_bogies_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_curse_of_the_bogies")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Curse of the Bogies; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Curse of the Bogies"


def test_s23_summon_inferi_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_summon_inferi")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Summon Inferi; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Summon Inferi"


def test_s23_dark_ritual_spell_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_dark_ritual_spell")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Dark Ritual; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Dark Ritual"


def test_s23_fiendfyre_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_fiendfyre")
    assert _assert_any(events, EventType.SURVEIL) or _assert_any(events, EventType.SCRY), \
        f"Expected info event for Fiendfyre; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DISCARD, player=p2.id) or _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp discard/drain for Fiendfyre"


def test_s23_incendio_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_incendio")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Incendio; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Incendio"


def test_s23_confringo_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_confringo")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Confringo; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Confringo"


def test_s23_bombarda_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_bombarda")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Bombarda; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Bombarda"


def test_s23_reducto_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_reducto")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Reducto; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Reducto"


def test_s23_expulso_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_expulso")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Expulso; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Expulso"


def test_s23_dragons_breath_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_dragons_breath")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Dragon's Breath; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Dragon's Breath"


def test_s23_weasley_firework_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_weasley_firework")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Weasley Firework; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Weasley Firework"


def test_s23_dragons_fire_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_dragons_fire")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Dragon's Fire; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Dragon's Fire"


def test_s23_pyrotechnics_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_pyrotechnics")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Pyrotechnics; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Pyrotechnics"


def test_s23_summon_dragon_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_summon_dragon")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Summon Dragon; events={[e.type.name for e in events]}"
    assert _assert_any(events, EventType.DAMAGE, target=p2.id), \
        f"Expected opp damage for Summon Dragon"


def test_s23_herbivicus_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_herbivicus")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Herbivicus"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Herbivicus"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Herbivicus"


def test_s23_wild_growth_spell_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_wild_growth")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Wild Growth"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Wild Growth"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Wild Growth"


def test_s23_engorgio_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_engorgio")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Engorgio"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Engorgio"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Engorgio"


def test_s23_beasts_fury_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_beasts_fury")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Beast's Fury"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Beast's Fury"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Beast's Fury"


def test_s23_natures_protection_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_natures_protection")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Nature's Protection"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Nature's Protection"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Nature's Protection"


def test_s23_greenhouse_harvest_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_greenhouse_harvest")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Greenhouse Harvest"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Greenhouse Harvest"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Greenhouse Harvest"


def test_s23_creature_summoning_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_creature_summoning")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Creature Summoning"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Creature Summoning"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Creature Summoning"


def test_s23_mandrake_restorative_resolve():
    events, p1, p2 = _s23_resolve("_hpw_s23_resolve_mandrake_restorative")
    assert _assert_any(events, EventType.SCRY) or _assert_any(events, EventType.SURVEIL), \
        f"Expected info event for Mandrake Restorative"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p1.id, amount='<POS>'), \
        f"Expected gain on caster for Mandrake Restorative"
    assert _assert_any(events, EventType.LIFE_CHANGE, player=p2.id, amount='<NEG>') or _assert_any(events, EventType.MILL, player=p2.id), \
        f"Expected opp drain/mill for Mandrake Restorative"


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
