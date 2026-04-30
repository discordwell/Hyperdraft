"""
Phase 2B vanilla-spell resolve tests (LCI/BLB/DSK/SPM).

Smoke tests that the cards wired in this phase emit the expected events
when their resolve functions are invoked. These are unit tests against
the resolve callbacks themselves — not full end-to-end stack tests —
because they're meant to catch regressions in the wiring at the resolve
function level, not the engine plumbing (which has its own tests in
test_spell_resolve.py).
"""

from src.engine.types import (
    GameState, EventType, Color, CardType, ZoneType, Characteristics,
)
from src.engine.targeting import Target


class _StubZone:
    def __init__(self, objs=None):
        self.objects = objs or []


class _StubObj:
    def __init__(self, controller='alice', name='X', zone=ZoneType.BATTLEFIELD,
                 types=None, obj_id=None):
        self.controller = controller
        self.card_def = None
        self.name = name
        self.zone = zone
        self.id = obj_id or ('obj-' + name)
        self.characteristics = Characteristics(types=types or set())


def _make_state(stack_objs=None, battlefield_objs=None, players=('alice', 'bob')):
    objects = {}
    stack_ids = []
    bf_ids = []
    for o in (stack_objs or []):
        objects[o.id] = o
        stack_ids.append(o.id)
    for o in (battlefield_objs or []):
        objects[o.id] = o
        bf_ids.append(o.id)
    state = GameState(
        players={p: None for p in players},
        zones={
            'stack': _StubZone(stack_ids),
            'battlefield': _StubZone(bf_ids),
        },
        objects=objects,
    )
    state.priority_player = 'alice'
    state.active_player = 'alice'
    return state


def test_hop_to_it_creates_three_rabbits():
    from src.cards.bloomburrow import hop_to_it_resolve
    spell = _StubObj(controller='alice', name='Hop to It', zone=ZoneType.STACK,
                     obj_id='spell1')
    state = _make_state(stack_objs=[spell])
    events = hop_to_it_resolve([], state)
    assert len(events) == 3
    for e in events:
        assert e.type == EventType.OBJECT_CREATED
        assert e.payload.get('power') == 1
        assert e.payload.get('toughness') == 1
        assert 'Rabbit' in e.payload.get('subtypes', [])
        assert Color.WHITE in e.payload.get('colors', [])
        assert CardType.CREATURE in e.payload.get('types', [])
    print('  ok: 3 Rabbit creature tokens emitted')


def test_pearl_of_wisdom_draws_two():
    from src.cards.bloomburrow import pearl_of_wisdom_resolve
    spell = _StubObj(controller='alice', name='Pearl of Wisdom',
                     zone=ZoneType.STACK, obj_id='spell1')
    state = _make_state(stack_objs=[spell])
    events = pearl_of_wisdom_resolve([], state)
    assert len(events) == 1
    assert events[0].type == EventType.DRAW
    assert events[0].payload.get('amount') == 2
    print('  ok: caster draws 2 cards')


def test_scales_of_shale_pumps_and_grants_keywords():
    from src.cards.bloomburrow import scales_of_shale_resolve
    spell = _StubObj(controller='alice', name='Scales of Shale',
                     zone=ZoneType.STACK, obj_id='spell1')
    state = _make_state(stack_objs=[spell])
    target = Target(id='c1', is_player=False)
    events = scales_of_shale_resolve([[target]], state)
    types = [e.type for e in events]
    assert EventType.PT_MODIFICATION in types
    assert types.count(EventType.GRANT_KEYWORD) == 2  # lifelink + indestructible
    pump = next(e for e in events if e.type == EventType.PT_MODIFICATION)
    assert pump.payload.get('power_mod') == 2
    assert pump.payload.get('toughness_mod') == 0
    keywords = {e.payload.get('keyword') for e in events
                if e.type == EventType.GRANT_KEYWORD}
    assert keywords == {'lifelink', 'indestructible'}
    print('  ok: +2/+0 + lifelink + indestructible')


def test_high_stride_pumps_grants_reach_and_untaps():
    from src.cards.bloomburrow import high_stride_resolve
    spell = _StubObj(controller='alice', name='High Stride',
                     zone=ZoneType.STACK, obj_id='spell1')
    state = _make_state(stack_objs=[spell])
    target = Target(id='c1', is_player=False)
    events = high_stride_resolve([[target]], state)
    types = [e.type for e in events]
    assert EventType.PT_MODIFICATION in types
    assert EventType.GRANT_KEYWORD in types
    assert EventType.UNTAP in types
    pump = next(e for e in events if e.type == EventType.PT_MODIFICATION)
    assert pump.payload.get('power_mod') == 1
    assert pump.payload.get('toughness_mod') == 3
    grant = next(e for e in events if e.type == EventType.GRANT_KEYWORD)
    assert grant.payload.get('keyword') == 'reach'
    untap = next(e for e in events if e.type == EventType.UNTAP)
    assert untap.payload.get('object_id') == 'c1'
    print('  ok: +1/+3 + reach + untap')


def test_overprotect_pumps_and_grants_three_keywords():
    from src.cards.bloomburrow import overprotect_resolve
    spell = _StubObj(controller='alice', name='Overprotect',
                     zone=ZoneType.STACK, obj_id='spell1')
    state = _make_state(stack_objs=[spell])
    target = Target(id='c1', is_player=False)
    events = overprotect_resolve([[target]], state)
    types = [e.type for e in events]
    assert types.count(EventType.PT_MODIFICATION) == 1
    assert types.count(EventType.GRANT_KEYWORD) == 3
    pump = next(e for e in events if e.type == EventType.PT_MODIFICATION)
    assert pump.payload.get('power_mod') == 3
    assert pump.payload.get('toughness_mod') == 3
    keywords = {e.payload.get('keyword') for e in events
                if e.type == EventType.GRANT_KEYWORD}
    assert keywords == {'trample', 'hexproof', 'indestructible'}
    print('  ok: +3/+3 + trample + hexproof + indestructible')


def test_glimmerburst_draws_two_and_creates_glimmer():
    from src.cards.duskmourn import glimmerburst_resolve
    spell = _StubObj(controller='alice', name='Glimmerburst',
                     zone=ZoneType.STACK, obj_id='spell1')
    state = _make_state(stack_objs=[spell])
    events = glimmerburst_resolve([], state)
    types = [e.type for e in events]
    assert EventType.DRAW in types
    assert EventType.OBJECT_CREATED in types
    draw = next(e for e in events if e.type == EventType.DRAW)
    assert draw.payload.get('amount') == 2
    token = next(e for e in events if e.type == EventType.OBJECT_CREATED)
    assert 'Glimmer' in token.payload.get('subtypes', [])
    assert CardType.ENCHANTMENT in token.payload.get('types', [])
    assert CardType.CREATURE in token.payload.get('types', [])
    print('  ok: draw 2 + 1/1 white Glimmer enchantment-creature')


def test_midnight_mayhem_creates_three_gremlins():
    from src.cards.duskmourn import midnight_mayhem_resolve
    spell = _StubObj(controller='alice', name='Midnight Mayhem',
                     zone=ZoneType.STACK, obj_id='spell1')
    state = _make_state(stack_objs=[spell])
    events = midnight_mayhem_resolve([], state)
    assert len(events) == 3
    for e in events:
        assert e.type == EventType.OBJECT_CREATED
        assert 'Gremlin' in e.payload.get('subtypes', [])
        assert Color.RED in e.payload.get('colors', [])
        assert CardType.CREATURE in e.payload.get('types', [])
    print('  ok: 3 Gremlin creature tokens emitted')


def test_villainous_wrath_life_loss_and_sweep():
    from src.cards.spider_man import villainous_wrath_resolve
    spell = _StubObj(controller='alice', name='Villainous Wrath',
                     zone=ZoneType.STACK, obj_id='spell1')
    bob_c1 = _StubObj(controller='bob', name='B1', types={CardType.CREATURE},
                      obj_id='B1')
    bob_c2 = _StubObj(controller='bob', name='B2', types={CardType.CREATURE},
                      obj_id='B2')
    alice_c = _StubObj(controller='alice', name='A1',
                       types={CardType.CREATURE}, obj_id='A1')
    state = _make_state(stack_objs=[spell],
                        battlefield_objs=[bob_c1, bob_c2, alice_c])
    target_player = Target(id='bob', is_player=True)
    events = villainous_wrath_resolve([[target_player]], state)
    # Expect 1 LIFE_CHANGE (-2) + 3 OBJECT_DESTROYED.
    types = [e.type for e in events]
    assert types.count(EventType.LIFE_CHANGE) == 1
    assert types.count(EventType.OBJECT_DESTROYED) == 3
    life = next(e for e in events if e.type == EventType.LIFE_CHANGE)
    assert life.payload == {'player': 'bob', 'amount': -2}
    destroyed_ids = {e.payload.get('object_id') for e in events
                     if e.type == EventType.OBJECT_DESTROYED}
    assert destroyed_ids == {'B1', 'B2', 'A1'}
    print('  ok: bob loses 2 life + all 3 creatures destroyed')


def test_villainous_wrath_no_target_player_skips_life():
    """If targets is empty, the life-loss step is skipped but sweep still runs."""
    from src.cards.spider_man import villainous_wrath_resolve
    spell = _StubObj(controller='alice', name='Villainous Wrath',
                     zone=ZoneType.STACK, obj_id='spell1')
    bob_c1 = _StubObj(controller='bob', name='B1', types={CardType.CREATURE},
                      obj_id='B1')
    state = _make_state(stack_objs=[spell], battlefield_objs=[bob_c1])
    events = villainous_wrath_resolve([], state)
    types = [e.type for e in events]
    assert EventType.LIFE_CHANGE not in types
    assert types.count(EventType.OBJECT_DESTROYED) == 1
    print('  ok: no target -> sweep only, no life loss')


def main():
    tests = [
        ('Hop to It (3 Rabbit tokens)', test_hop_to_it_creates_three_rabbits),
        ('Pearl of Wisdom (draw 2)', test_pearl_of_wisdom_draws_two),
        ('Scales of Shale (+2/+0 + 2 keywords)',
         test_scales_of_shale_pumps_and_grants_keywords),
        ('High Stride (+1/+3 + reach + untap)',
         test_high_stride_pumps_grants_reach_and_untaps),
        ('Overprotect (+3/+3 + 3 keywords)',
         test_overprotect_pumps_and_grants_three_keywords),
        ('Glimmerburst (draw 2 + Glimmer)',
         test_glimmerburst_draws_two_and_creates_glimmer),
        ('Midnight Mayhem (3 Gremlin tokens)',
         test_midnight_mayhem_creates_three_gremlins),
        ('Villainous Wrath (life loss + sweep)',
         test_villainous_wrath_life_loss_and_sweep),
        ('Villainous Wrath (no target, sweep only)',
         test_villainous_wrath_no_target_player_skips_life),
    ]
    print('=== Phase 2B vanilla-spell resolves ===')
    failed = 0
    for label, fn in tests:
        try:
            print(f'-- {label}')
            fn()
        except AssertionError as e:
            failed += 1
            print(f'  FAIL: {e}')
        except Exception as e:
            failed += 1
            print(f'  ERROR: {e!r}')
    total = len(tests)
    if failed:
        print(f'=== {total - failed}/{total} passed; {failed} failed ===')
        raise SystemExit(1)
    print(f'=== {total}/{total} passed ===')


if __name__ == '__main__':
    main()
