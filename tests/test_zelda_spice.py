"""
Legend of Zelda Spice Pass Tests (Phase A1)

Validates the format-defining cards added in
`/Users/discordwell/.claude/plans/zld_spice_pass.md`.
Phase A1 — within current engine, no new helpers.

Cards covered:
- Triforce of Power / Wisdom / Courage (REWIRE — were unwired stubs)
- Hylian Shield (REWIRE — was unwired equipment)
- Master Kohga (REWIRE — impulse-draw on upkeep)
- Link, Hero of the Wild (NEW — Stoneforge-style Equipment tutor on a body)
"""

import sys
sys.path.insert(0, '/Users/discordwell/Projects/HYPERDRAFT')

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.legend_of_zelda import LEGEND_OF_ZELDA_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the Star Wars spice test harness shape.

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE
    to battlefield, runs setup exactly once via the pipeline (the correct
    path)."""
    card_def = LEGEND_OF_ZELDA_CARDS[card_name]
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
# Triforce of Power
# ============================================================================

def test_triforce_of_power_loads():
    """Setup_interceptors registers anthem + activated ability descriptor."""
    print("\n=== Triforce of Power: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tof = _put_on_battlefield(game, p1, "Triforce of Power")
    assert tof.zone == ZoneType.BATTLEFIELD
    # Anthem interceptor + activated ability descriptor (stored on obj.state).
    activated = getattr(tof.state, 'activated_abilities', None)
    assert activated, "Expected an activated ability on Triforce of Power"
    print(f"  Interceptors: {len(tof.interceptor_ids)}  Activated abilities: {len(activated)}")


def test_triforce_of_power_anthem_buffs_other_creatures():
    """Other creatures you control get +1/+0 via QUERY_POWER intercept."""
    print("\n=== Triforce of Power: anthem ===")
    game = Game()
    p1 = game.add_player("Alice")
    knight = _put_on_battlefield(game, p1, "Hyrule Knight")
    base_p = get_power(knight, game.state)
    _put_on_battlefield(game, p1, "Triforce of Power")
    new_p = get_power(knight, game.state)
    assert new_p == base_p + 1, f"Expected Knight power +1: {base_p}→{new_p}"
    print(f"  Hyrule Knight power: {base_p} -> {new_p}")


# ============================================================================
# Triforce of Wisdom
# ============================================================================

def test_triforce_of_wisdom_loads():
    """Setup registers draw-trigger interceptor + activated ability."""
    print("\n=== Triforce of Wisdom: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tof = _put_on_battlefield(game, p1, "Triforce of Wisdom")
    assert tof.zone == ZoneType.BATTLEFIELD
    activated = getattr(tof.state, 'activated_abilities', None)
    assert activated, "Expected an activated ability on Triforce of Wisdom"


def test_triforce_of_wisdom_draw_triggers_scry():
    """Own draw fires a scry placeholder event (ACTIVATE/scry shape)."""
    print("\n=== Triforce of Wisdom: draw -> scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Triforce of Wisdom")

    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p1.id, 'amount': 1},
    ))
    # The scry placeholder is an ACTIVATE event with payload['action']='scry'.
    scry_events = [
        e for e in game.state.event_log
        if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry'
    ]
    assert scry_events, "Expected a scry placeholder event after own draw"
    assert scry_events[-1].payload.get('amount') == 1
    print(f"  Scry events after draw: {len(scry_events)}")


def test_triforce_of_wisdom_opp_draw_no_scry():
    """Opponent draw does NOT fire the wisdom scry."""
    print("\n=== Triforce of Wisdom: opp draw -> no scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Triforce of Wisdom")

    before = sum(
        1 for e in game.state.event_log
        if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry'
    )
    game.emit(Event(
        type=EventType.DRAW,
        payload={'player': p2.id, 'amount': 1},
    ))
    after = sum(
        1 for e in game.state.event_log
        if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry'
    )
    assert after == before, f"Opp draw triggered scry: {before}->{after}"


# ============================================================================
# Triforce of Courage
# ============================================================================

def test_triforce_of_courage_loads():
    """Setup registers vigilance grant + activated ability."""
    print("\n=== Triforce of Courage: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tof = _put_on_battlefield(game, p1, "Triforce of Courage")
    assert tof.zone == ZoneType.BATTLEFIELD
    activated = getattr(tof.state, 'activated_abilities', None)
    assert activated, "Expected an activated ability on Triforce of Courage"


def test_triforce_of_courage_creatures_have_vigilance():
    """Creatures you control gain vigilance via QUERY_ABILITIES."""
    print("\n=== Triforce of Courage: vigilance grant ===")
    game = Game()
    p1 = game.add_player("Alice")
    knight = _put_on_battlefield(game, p1, "Hyrule Knight")
    assert not has_ability(knight, "vigilance", game.state), (
        "Knight should not pre-have vigilance"
    )
    _put_on_battlefield(game, p1, "Triforce of Courage")
    assert has_ability(knight, "vigilance", game.state), (
        "Expected vigilance after Triforce of Courage ETB"
    )
    print(f"  Hyrule Knight gained vigilance")


# ============================================================================
# Hylian Shield
# ============================================================================

def test_hylian_shield_loads():
    """make_equipment_setup registers PT-mod + ward + equip-cost ability."""
    print("\n=== Hylian Shield: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    shield = _put_on_battlefield(game, p1, "Hylian Shield")
    assert shield.zone == ZoneType.BATTLEFIELD
    # Has equip activated ability and ATTACH listeners.
    activated = getattr(shield.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Hylian Shield"
    assert len(shield.interceptor_ids) >= 2, (
        f"Expected PT + ward interceptors; got {len(shield.interceptor_ids)}"
    )


def test_hylian_shield_pt_mod_on_attach():
    """After ATTACH, equipped creature reads +1/+3 via PT query aggregation."""
    print("\n=== Hylian Shield: +1/+3 on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    shield = _put_on_battlefield(game, p1, "Hylian Shield")
    knight = _put_on_battlefield(game, p1, "Hyrule Knight")
    base_p = get_power(knight, game.state)
    base_t = get_toughness(knight, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': shield.id, 'target_id': knight.id},
        source=shield.id,
    ))

    new_p = get_power(knight, game.state)
    new_t = get_toughness(knight, game.state)
    assert new_p == base_p + 1, f"Expected power +1: {base_p}→{new_p}"
    assert new_t == base_t + 3, f"Expected toughness +3: {base_t}→{new_t}"
    print(f"  Hyrule Knight: {base_p}/{base_t} -> {new_p}/{new_t}")


# ============================================================================
# Master Kohga
# ============================================================================

def test_master_kohga_loads():
    print("\n=== Master Kohga: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kohga = _put_on_battlefield(game, p1, "Master Kohga")
    assert kohga.zone == ZoneType.BATTLEFIELD
    assert kohga.interceptor_ids, "Master Kohga should register an upkeep trigger"


def test_master_kohga_upkeep_emits_exile_top_play():
    """Own upkeep emits EXILE_TOP_PLAY with caster=controller."""
    print("\n=== Master Kohga: upkeep -> impulse draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Master Kohga")

    # Per spice-pass gotcha #8: make_upkeep_trigger filters on state.active_player,
    # not the payload's active_player field.
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))

    exile_events = [
        e for e in game.state.event_log
        if e.type == EventType.EXILE_TOP_PLAY and e.payload.get('caster') == p1.id
    ]
    assert exile_events, (
        f"Expected EXILE_TOP_PLAY with caster={p1.id}; "
        f"got types {_emitted_types(game)[-10:]}"
    )
    print(f"  EXILE_TOP_PLAY events: {len(exile_events)}")


def test_master_kohga_opp_upkeep_no_trigger():
    """Opponent upkeep does not fire Kohga's impulse-draw."""
    print("\n=== Master Kohga: opp upkeep -> no fire ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Master Kohga")

    game.state.active_player = p2.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    exile_events = [
        e for e in game.state.event_log
        if e.type == EventType.EXILE_TOP_PLAY and e.payload.get('caster') == p1.id
    ]
    assert not exile_events, "Kohga fired during opp upkeep"


# ============================================================================
# Link, Hero of the Wild
# ============================================================================

def test_link_hero_of_the_wild_loads():
    """Setup registers self-trample+haste + ETB tutor + attack pump."""
    print("\n=== Link, Hero of the Wild: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    link = _put_on_battlefield(game, p1, "Link, Hero of the Wild")
    assert link.zone == ZoneType.BATTLEFIELD
    assert len(link.interceptor_ids) >= 3, (
        f"Expected keyword + etb + attack; got {len(link.interceptor_ids)}"
    )


def test_link_hero_of_the_wild_etb_tutors_equipment():
    """ETB emits SEARCH_LIBRARY for an Equipment with MV<=3 onto battlefield."""
    print("\n=== Link, Hero of the Wild: ETB tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Link, Hero of the Wild")

    search_events = [
        e for e in game.state.event_log
        if e.type == EventType.SEARCH_LIBRARY
        and e.payload.get('subtype') == 'Equipment'
        and e.payload.get('destination') == 'battlefield'
    ]
    assert search_events, (
        f"Expected ETB SEARCH_LIBRARY for Equipment; recent={_emitted_types(game)[-10:]}"
    )
    assert search_events[-1].payload.get('mana_value_max') == 3
    print(f"  SEARCH_LIBRARY (Equipment, MV<=3, battlefield) events: {len(search_events)}")


def test_link_hero_of_the_wild_attack_scales_by_artifact_count():
    """Attack trigger emits PT_MOD +N/+N where N = artifacts you control."""
    print("\n=== Link, Hero of the Wild: attack scale ===")
    game = Game()
    p1 = game.add_player("Alice")
    link = _put_on_battlefield(game, p1, "Link, Hero of the Wild")
    # Add two non-Link artifacts.
    _put_on_battlefield(game, p1, "Triforce of Power")
    _put_on_battlefield(game, p1, "Hylian Shield")

    # Snapshot event log size before attack to filter out setup-time noise.
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': link.id, 'attacker': link.id, 'controller': p1.id},
        source=link.id,
    ))

    after_events = game.state.event_log[before:]
    pt_mods = [
        e for e in after_events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == link.id
    ]
    assert pt_mods, "Expected attack-trigger PT_MODIFICATION on Link"
    n = pt_mods[-1].payload.get('power_mod')
    # 2 artifacts (Triforce + Shield) plus Link self has 0 artifacts (Link is
    # creature). Expect power_mod == 2.
    assert n == 2, f"Expected +2/+2 with 2 artifacts; got +{n}"
    print(f"  Link attack pump with 2 artifacts: +{n}/+{n}")


def test_link_hero_of_the_wild_attack_zero_artifacts_no_pump():
    """Edge: 0 artifacts means no PT_MODIFICATION event (effect returns [])."""
    print("\n=== Link, Hero of the Wild: zero artifacts ===")
    game = Game()
    p1 = game.add_player("Alice")
    link = _put_on_battlefield(game, p1, "Link, Hero of the Wild")
    # Do NOT add any artifacts.

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': link.id, 'attacker': link.id, 'controller': p1.id},
        source=link.id,
    ))
    after_events = game.state.event_log[before:]
    pt_mods = [
        e for e in after_events
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == link.id
    ]
    assert not pt_mods, f"Expected NO PT_MOD with 0 artifacts; got {len(pt_mods)}"


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
