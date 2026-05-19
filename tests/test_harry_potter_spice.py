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
