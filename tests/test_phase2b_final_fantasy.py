"""
Phase 2B vanilla-spell wiring smoke tests for src/cards/final_fantasy.py.

Each test verifies that the ``resolve=`` callback wired in Phase 2B emits
the right Event(s) for representative card text. These are unit-level checks
on the resolve callable contract — they do not run the full stack pipeline,
which keeps the suite fast and isolates the wiring concern.

Run directly:

    python tests/test_phase2b_final_fantasy.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
)
from src.engine.targeting import Target
from src.cards import final_fantasy as fin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game_with_caster():
    """Return (game, caster_id) with one player set up."""
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    game.start_game()
    return game, p1.id


def _put_spell_on_stack(game, caster_id: str, name: str):
    """Drop a stub spell GameObject on the stack so resolve helpers can find
    the caster via ``_ff_caster_id``.
    """
    from src.engine.types import GameObject, Characteristics, ObjectState, new_id

    spell = GameObject(
        id=new_id(),
        name=name,
        characteristics=Characteristics(),
        state=ObjectState(),
        zone=ZoneType.STACK,
        controller=caster_id,
        owner=caster_id,
    )
    game.state.objects[spell.id] = spell
    stack_zone = game.state.zones.get('stack')
    if stack_zone is not None:
        stack_zone.objects.append(spell.id)
    return spell


def _make_creature(game, controller_id, name="Bear", power=2, toughness=2,
                   subtypes=None, types=None):
    """Drop a vanilla creature on the battlefield."""
    from src.engine.types import GameObject, Characteristics, ObjectState, new_id

    types = set(types or [CardType.CREATURE])
    obj = GameObject(
        id=new_id(),
        name=name,
        characteristics=Characteristics(
            types=types,
            subtypes=set(subtypes or []),
            power=power,
            toughness=toughness,
            colors={Color.GREEN},
        ),
        state=ObjectState(),
        zone=ZoneType.BATTLEFIELD,
        controller=controller_id,
        owner=controller_id,
    )
    game.state.objects[obj.id] = obj
    bf = game.state.zones.get('battlefield')
    if bf is not None:
        bf.objects.append(obj.id)
    return obj


# ---------------------------------------------------------------------------
# Tests — composable helper wiring
# ---------------------------------------------------------------------------

def test_travel_the_overworld_draws_four():
    print("\n=== Test: Travel the Overworld -> draw 4 ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Travel the Overworld")
    events = fin.TRAVEL_THE_OVERWORLD.resolve([], game.state)
    assert len(events) == 1, events
    e = events[0]
    assert e.type == EventType.DRAW
    assert e.payload['amount'] == 4
    assert e.payload['player'] == caster
    print("PASS: emits DRAW(4) for caster")


def test_aerith_rescue_mode0_creates_three_heroes():
    print("\n=== Test: Aerith Rescue Mission mode 0 ===")
    game, caster = _make_game_with_caster()
    spell = _put_spell_on_stack(game, caster, "Aerith Rescue Mission")
    spell.chosen_mode = 0
    events = fin.AERITH_RESCUE_MISSION.resolve([], game.state)
    assert len(events) == 3, events
    for e in events:
        assert e.type == EventType.OBJECT_CREATED
        assert e.payload['name'] == "Hero"
        assert e.payload['power'] == 1 and e.payload['toughness'] == 1
        assert CardType.CREATURE in e.payload['types']
    print("PASS: emits 3 Hero token creations")


def test_moogles_valor_one_token_per_creature():
    print("\n=== Test: Moogles' Valor ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Moogles' Valor")
    c1 = _make_creature(game, caster, "Bear")
    c2 = _make_creature(game, caster, "Wolf")
    events = fin.MOOGLES_VALOR.resolve([], game.state)
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED]
    keyword_events = [e for e in events if e.type == EventType.GRANT_KEYWORD]
    assert len(token_events) == 2, token_events
    assert len(keyword_events) == 2, keyword_events
    for e in token_events:
        assert e.payload['name'] == 'Moogle'
        assert Color.WHITE in e.payload['colors']
        assert e.payload['power'] == 1 and e.payload['toughness'] == 2
    for e in keyword_events:
        assert e.payload['keyword'] == 'indestructible'
    print(f"PASS: 2 Moogle tokens + 2 indestructible grants for {len(token_events)} creatures")


def test_slash_of_light_damage_count():
    print("\n=== Test: Slash of Light ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Slash of Light")
    _make_creature(game, caster, "Bear")
    _make_creature(game, caster, "Wolf")
    # Add an Equipment artifact
    from src.engine.types import GameObject, Characteristics, ObjectState, new_id
    eq = GameObject(
        id=new_id(), name="Sword",
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes={'Equipment'},
        ),
        state=ObjectState(),
        zone=ZoneType.BATTLEFIELD,
        controller=caster, owner=caster,
    )
    game.state.objects[eq.id] = eq
    game.state.zones['battlefield'].objects.append(eq.id)
    # Target a creature
    target_obj = _make_creature(game, caster, "Victim")
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = fin.SLASH_OF_LIGHT.resolve(targets, game.state)
    # 3 creatures + 1 equipment = 4 dmg expected
    dmg_events = [e for e in events if e.type == EventType.DAMAGE]
    assert len(dmg_events) == 1, dmg_events
    assert dmg_events[0].payload['amount'] == 4
    assert dmg_events[0].payload['target'] == target_obj.id
    print("PASS: 4 damage = 3 creatures + 1 equipment")


def test_louisoix_sacrifice_emits_counter():
    print("\n=== Test: Louisoix's Sacrifice counter event ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Louisoix's Sacrifice")
    targets = [[Target(id="some_spell", is_player=False)]]
    events = fin.LOUISOIXS_SACRIFICE.resolve(targets, game.state)
    assert len(events) == 1, events
    assert events[0].type == EventType.COUNTER_SPELL
    assert events[0].payload['target_id'] == 'some_spell'
    print("PASS: emits COUNTER_SPELL")


def test_magic_damper_pump_hexproof_untap():
    print("\n=== Test: Magic Damper ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Magic Damper")
    target_obj = _make_creature(game, caster, "MyBear")
    targets = [[Target(id=target_obj.id, is_player=False)]]
    events = fin.MAGIC_DAMPER.resolve(targets, game.state)
    types = {e.type for e in events}
    assert EventType.PT_MODIFICATION in types
    assert EventType.GRANT_KEYWORD in types
    assert EventType.UNTAP in types
    pt_e = next(e for e in events if e.type == EventType.PT_MODIFICATION)
    assert pt_e.payload['power_mod'] == 1 and pt_e.payload['toughness_mod'] == 1
    print("PASS: PT_MODIFICATION + GRANT_KEYWORD(hexproof) + UNTAP all emitted")


def test_blitzball_shot_pump_and_trample():
    print("\n=== Test: Blitzball Shot ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Blitzball Shot")
    obj = _make_creature(game, caster, "Friend")
    targets = [[Target(id=obj.id, is_player=False)]]
    events = fin.BLITZBALL_SHOT.resolve(targets, game.state)
    pt_e = next(e for e in events if e.type == EventType.PT_MODIFICATION)
    kw_e = next(e for e in events if e.type == EventType.GRANT_KEYWORD)
    assert pt_e.payload['power_mod'] == 3 and pt_e.payload['toughness_mod'] == 3
    assert kw_e.payload['keyword'] == 'trample'
    print("PASS: +3/+3 + trample")


def test_selfdestruct_xx_damage():
    print("\n=== Test: Self-Destruct ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Self-Destruct")
    src = _make_creature(game, caster, "Boom", power=3, toughness=3)
    other = _make_creature(game, caster, "Victim")
    targets = [
        [Target(id=src.id, is_player=False)],
        [Target(id=other.id, is_player=False)],
    ]
    events = fin.SELFDESTRUCT.resolve(targets, game.state)
    dmg = [e for e in events if e.type == EventType.DAMAGE]
    assert len(dmg) == 2, dmg
    amounts = sorted(e.payload['amount'] for e in dmg)
    assert amounts == [3, 3], amounts
    targets_set = {e.payload['target'] for e in dmg}
    assert targets_set == {src.id, other.id}
    print("PASS: 3 damage to both source and other target")


def test_evil_reawakened_emits_return_and_counters():
    print("\n=== Test: Evil Reawakened ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Evil Reawakened")
    targets = [[Target(id="some_creature", is_player=False)]]
    events = fin.EVIL_REAWAKENED.resolve(targets, game.state)
    types = [e.type for e in events]
    assert EventType.RETURN_FROM_GRAVEYARD in types
    counter_e = next(e for e in events if e.type == EventType.COUNTER_ADDED)
    assert counter_e.payload['amount'] == 2
    assert counter_e.payload['counter_type'] == '+1/+1'
    print("PASS: RETURN_FROM_GRAVEYARD + 2 +1/+1 counters")


def test_fight_on_returns_two_to_hand():
    print("\n=== Test: Fight On! ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Fight On!")
    targets = [[
        Target(id="card_a", is_player=False),
        Target(id="card_b", is_player=False),
    ]]
    events = fin.FIGHT_ON.resolve(targets, game.state)
    assert len(events) == 2
    for e in events:
        assert e.type == EventType.RETURN_TO_HAND_FROM_GRAVEYARD
    print("PASS: 2 RETURN_TO_HAND_FROM_GRAVEYARD events")


def test_ultima_destroys_all_artifacts_and_creatures():
    print("\n=== Test: Ultima ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Ultima")
    c1 = _make_creature(game, caster, "Foo")
    # Add an artifact and a non-target enchantment.
    from src.engine.types import GameObject, Characteristics, ObjectState, new_id
    art = GameObject(
        id=new_id(), name="Art",
        characteristics=Characteristics(types={CardType.ARTIFACT}),
        state=ObjectState(),
        zone=ZoneType.BATTLEFIELD,
        controller=caster, owner=caster,
    )
    enc = GameObject(
        id=new_id(), name="Enc",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}),
        state=ObjectState(),
        zone=ZoneType.BATTLEFIELD,
        controller=caster, owner=caster,
    )
    game.state.objects[art.id] = art
    game.state.objects[enc.id] = enc
    game.state.zones['battlefield'].objects.extend([art.id, enc.id])
    events = fin.ULTIMA.resolve([], game.state)
    destroyed_ids = {e.payload['object_id'] for e in events
                     if e.type == EventType.OBJECT_DESTROYED}
    assert c1.id in destroyed_ids
    assert art.id in destroyed_ids
    assert enc.id not in destroyed_ids  # enchantments are spared
    print(f"PASS: destroyed {len(destroyed_ids)} permanents (creature + artifact)")


def test_haste_magic_pump_haste_and_impulse():
    print("\n=== Test: Haste Magic ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Haste Magic")
    obj = _make_creature(game, caster, "Friend")
    targets = [[Target(id=obj.id, is_player=False)]]
    events = fin.HASTE_MAGIC.resolve(targets, game.state)
    types = [e.type for e in events]
    assert EventType.PT_MODIFICATION in types
    assert EventType.GRANT_KEYWORD in types
    assert EventType.IMPULSE_DRAW in types
    pt_e = next(e for e in events if e.type == EventType.PT_MODIFICATION)
    assert pt_e.payload['power_mod'] == 3 and pt_e.payload['toughness_mod'] == 1
    kw_e = next(e for e in events if e.type == EventType.GRANT_KEYWORD)
    assert kw_e.payload['keyword'] == 'haste'
    print("PASS: +3/+1 + haste + IMPULSE_DRAW")


def test_chocobo_kick_unkicked_uses_power():
    print("\n=== Test: Chocobo Kick (not kicked) ===")
    game, caster = _make_game_with_caster()
    _put_spell_on_stack(game, caster, "Chocobo Kick")
    src = _make_creature(game, caster, "Boko", power=4, toughness=4)
    victim = _make_creature(game, caster, "Foe")
    targets = [
        [Target(id=src.id, is_player=False)],
        [Target(id=victim.id, is_player=False)],
    ]
    events = fin.CHOCOBO_KICK.resolve(targets, game.state)
    assert len(events) == 1
    assert events[0].type == EventType.DAMAGE
    assert events[0].payload['amount'] == 4
    print("PASS: 4 damage (= source power)")


def test_chocobo_kick_kicked_doubles():
    print("\n=== Test: Chocobo Kick (kicked) ===")
    game, caster = _make_game_with_caster()
    spell = _put_spell_on_stack(game, caster, "Chocobo Kick")
    spell.state.kicked = True
    src = _make_creature(game, caster, "Boko", power=4, toughness=4)
    victim = _make_creature(game, caster, "Foe")
    targets = [
        [Target(id=src.id, is_player=False)],
        [Target(id=victim.id, is_player=False)],
    ]
    events = fin.CHOCOBO_KICK.resolve(targets, game.state)
    assert events[0].payload['amount'] == 8
    print("PASS: kicked doubles damage to 8")


def test_left_cards_have_no_resolve():
    """Cards intentionally left for engine gaps must keep resolve=None."""
    print("\n=== Test: engine-gap cards remain unwired ===")
    left = [
        'MEMORIES_RETURNING', 'STOLEN_UNIFORM', 'VINCENTS_LIMIT_BREAK',
        'RANDOM_ENCOUNTER', 'UNEXPECTED_REQUEST', 'CLASH_OF_THE_EIKONS',
        'ISHGARD_THE_HOLY_SEE', 'JIDOOR_ARISTOCRATIC_CAPITAL',
        'LINDBLUM_INDUSTRIAL_REGENCY', 'MIDGAR_CITY_OF_MAKO',
        'ZANARKAND_ANCIENT_METROPOLIS',
    ]
    for var in left:
        cd = getattr(fin, var)
        assert cd.resolve is None, f"{var} should have resolve=None"
    print(f"PASS: {len(left)} engine-gap cards intact")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_travel_the_overworld_draws_four,
        test_aerith_rescue_mode0_creates_three_heroes,
        test_moogles_valor_one_token_per_creature,
        test_slash_of_light_damage_count,
        test_louisoix_sacrifice_emits_counter,
        test_magic_damper_pump_hexproof_untap,
        test_blitzball_shot_pump_and_trample,
        test_selfdestruct_xx_damage,
        test_evil_reawakened_emits_return_and_counters,
        test_fight_on_returns_two_to_hand,
        test_ultima_destroys_all_artifacts_and_creatures,
        test_haste_magic_pump_haste_and_impulse,
        test_chocobo_kick_unkicked_uses_power,
        test_chocobo_kick_kicked_doubles,
        test_left_cards_have_no_resolve,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL: {t.__name__}: {exc}")
    print()
    print("=" * 60)
    if failures:
        print(f"{failures} TEST(S) FAILED")
        sys.exit(1)
    print("ALL PHASE 2B FF SMOKE TESTS PASSED!")
    print("=" * 60)
