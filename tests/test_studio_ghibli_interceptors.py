"""Interceptor verification for Studio Ghibli set.

Catches the "depths trap": interceptor is wired but effect_fn returns [] silently.
For each card with a real implementation restored after the slice-6 retrofit
removal, this file fires the trigger via the engine and asserts a real (non-zero,
non-bogus) event emits.

Generated after the slice-6A/B/C/D wrapper purge — see commit history. Every
test verifies a REAL effect that matches the card's rules text, not a marker
scry/drain.
"""

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "studio_ghibli",
    str(PROJECT_ROOT / "src/cards/custom/studio_ghibli.py")
)
studio_ghibli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio_ghibli)
STUDIO_GHIBLI_CARDS = studio_ghibli.STUDIO_GHIBLI_CARDS

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, get_power, get_toughness,
)


def _make_game_with_two_players():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    return game, p1, p2


def _put_on_battlefield(game, owner, card_name, *, emit_etb=True):
    card_def = STUDIO_GHIBLI_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    if emit_etb:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone': 'hand',
                'to_zone': 'battlefield',
                'from_zone_type': ZoneType.HAND,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=obj.id,
            controller=owner.id,
        ))
    return obj


# ============================================================================
# Cards skipped: rules text the engine does not yet express in a way we can
# auto-test. These are not failures of the card definition; they are gaps.
# ============================================================================
SKIPPED_CARDS = {
    "Moss-Covered Golem": "conditional hexproof grant needs gate; we keep card vanilla",
    "Forest Spirit, Shishigami": "global +2/+2 anthem with leaves-bf cleanup not modelled",
    "Chibi Totoro": "phase in/out tutor on entry requires phase-in event handler",
    "Cursed Swamp": "ETB-curse-on-target needs chosen-target capture",
}


# ----------------------------------------------------------------------------
# ETB life-drain / lifegain cards
# ----------------------------------------------------------------------------

def test_corrupted_kodama_etb_drains_each_opp_and_gains_self():
    game, p1, p2 = _make_game_with_two_players()
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Corrupted Kodama")
    new = game.state.event_log[before:]
    life_events = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id]
    assert life_events, f"Expected LIFE_CHANGE from Corrupted Kodama; got {[e.type.name for e in new]}"
    caster_gain = [e for e in life_events if e.payload.get('player') == p1.id and e.payload.get('amount', 0) > 0]
    opp_loss = [e for e in life_events if e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert caster_gain, f"Expected caster lifegain; got {life_events}"
    assert opp_loss, f"Expected opp life loss; got {life_events}"
    print("PASSED: Corrupted Kodama drains opp and gains self")


def test_bathhouse_servant_etb_gains_2_life():
    game, p1, _ = _make_game_with_two_players()
    start = p1.life
    _put_on_battlefield(game, p1, "Bathhouse Servant")
    assert p1.life >= start + 2, f"Expected +2 life, got {p1.life - start}"
    print("PASSED: Bathhouse Servant gains 2 life")


def test_valley_villager_etb_gains_2_life():
    game, p1, _ = _make_game_with_two_players()
    start = p1.life
    _put_on_battlefield(game, p1, "Valley Villager")
    assert p1.life >= start + 2, f"Expected +2 life, got {p1.life - start}"
    print("PASSED: Valley Villager gains 2 life")


# ----------------------------------------------------------------------------
# Tutor / search-library cards
# ----------------------------------------------------------------------------

def test_catbus_etb_search_for_basic_land():
    game, p1, _ = _make_game_with_two_players()
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Catbus, Forest Transport")
    new = game.state.event_log[before:]
    searches = [e for e in new if e.type == EventType.SEARCH_LIBRARY and e.source == obj.id]
    assert searches, f"Expected SEARCH_LIBRARY from Catbus; got {[e.type.name for e in new]}"
    assert searches[0].payload.get('filter') == 'basic_land'
    print("PASSED: Catbus ETB searches for basic land")


def test_wild_wolf_etb_search_for_wolf():
    game, p1, _ = _make_game_with_two_players()
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Wild Wolf")
    new = game.state.event_log[before:]
    searches = [e for e in new if e.type == EventType.SEARCH_LIBRARY and e.source == obj.id]
    assert searches, f"Expected SEARCH_LIBRARY from Wild Wolf; got {[e.type.name for e in new]}"
    assert searches[0].payload.get('subtype') == 'Wolf'
    print("PASSED: Wild Wolf ETB searches for Wolf")


# ----------------------------------------------------------------------------
# Token creation cards
# ----------------------------------------------------------------------------

def test_sheeta_etb_creates_laputan_amulet():
    game, p1, _ = _make_game_with_two_players()
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Sheeta, Princess of Laputa")
    new = game.state.event_log[before:]
    creates = [e for e in new if e.type == EventType.OBJECT_CREATED
               and e.source == obj.id
               and e.payload.get('name') == 'Laputan Amulet']
    assert creates, f"Expected Laputan Amulet token; got {[e.type.name for e in new]}"
    print("PASSED: Sheeta creates Laputan Amulet token")


# ----------------------------------------------------------------------------
# Death triggers
# ----------------------------------------------------------------------------

def test_spirit_of_vengeance_death_drains_opp():
    game, p1, p2 = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Spirit of Vengeance", emit_etb=False)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'battlefield',
            'to_zone': 'graveyard',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=obj.id,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    drains = [e for e in new if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id
              and e.payload.get('amount', 0) == -2]
    assert drains, f"Expected -2 to opp on death; got {[e.type.name for e in new]}"
    print("PASSED: Spirit of Vengeance death drains opp 2")


def test_baby_ohmu_death_searches_for_forest():
    game, p1, _ = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Baby Ohmu", emit_etb=False)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'battlefield',
            'to_zone': 'graveyard',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=obj.id,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    searches = [e for e in new if e.type == EventType.SEARCH_LIBRARY and e.source == obj.id]
    assert searches, f"Expected SEARCH_LIBRARY on Baby Ohmu death; got {[e.type.name for e in new]}"
    assert searches[0].payload.get('subtype') == 'Forest'
    print("PASSED: Baby Ohmu death searches for Forest")


def test_toxic_jungle_lurker_death_puts_counters_on_opp_creatures():
    game, p1, p2 = _make_game_with_two_players()
    opp_bear = game.create_object(
        name="Opp Bear", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE}, subtypes={'Bear'},
                                         power=2, toughness=2, mana_cost=""),
        card_def=None,
    )
    obj = _put_on_battlefield(game, p1, "Toxic Jungle Lurker", emit_etb=False)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'battlefield',
            'to_zone': 'graveyard',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=obj.id,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    minus_counters = [e for e in new if e.type == EventType.COUNTER_ADDED
                      and e.payload.get('counter_type') == '-1/-1'
                      and e.payload.get('object_id') == opp_bear.id]
    assert minus_counters, f"Expected -1/-1 counter on opp bear; got {[e.type.name for e in new]}"
    print("PASSED: Toxic Jungle Lurker death puts -1/-1 counter on opp creature")


# ----------------------------------------------------------------------------
# Static P/T effects
# ----------------------------------------------------------------------------

def test_insect_swarm_grows_per_other_insect():
    game, p1, _ = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Insect Swarm", emit_etb=False)
    assert get_power(obj, game.state) == 3
    for i in range(2):
        game.create_object(
            name=f"Insect {i}", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE},
                                             subtypes={'Insect'},
                                             power=1, toughness=1, mana_cost=""),
            card_def=None,
        )
    p_final = get_power(obj, game.state)
    assert p_final == 5, f"Expected 5 with 2 others; got {p_final}"
    print("PASSED: Insect Swarm +1/+1 per other Insect")


def test_ancient_tree_spirit_natures_wrath():
    game, p1, _ = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Ancient Tree Spirit", emit_etb=False)
    for i in range(2):
        game.create_object(
            name=f"Forest {i}", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.LAND},
                                             subtypes={'Forest'}, mana_cost=""),
            card_def=None,
        )
    p = get_power(obj, game.state)
    assert p == 5, f"Expected 5 (3 base + 2 forests); got {p}"
    print("PASSED: Ancient Tree Spirit Nature's Wrath +1/+1 per Forest")


def test_dark_forest_creature_natures_wrath_power_only():
    game, p1, _ = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Dark Forest Creature", emit_etb=False)
    for i in range(3):
        game.create_object(
            name=f"Forest {i}", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.LAND},
                                             subtypes={'Forest'}, mana_cost=""),
            card_def=None,
        )
    p = get_power(obj, game.state)
    assert p == 5, f"Expected 5 (2 base + 3 forests); got {p}"
    print("PASSED: Dark Forest Creature +1/+0 per Forest")


def test_jiji_witch_lord_buffs_other_witches():
    game, p1, _ = _make_game_with_two_players()
    jiji = _put_on_battlefield(game, p1, "Jiji, Black Cat Familiar", emit_etb=False)
    witch = game.create_object(
        name="Witch X", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE},
                                         subtypes={'Witch', 'Human'},
                                         power=1, toughness=1, mana_cost=""),
        card_def=None,
    )
    wp = get_power(witch, game.state)
    assert wp == 2, f"Expected witch power 2; got {wp}"
    jp = get_power(jiji, game.state)
    assert jp == 1, f"Jiji shouldn't buff self; got {jp}"
    print("PASSED: Jiji buffs Witches but not self")


def test_seaplane_mechanic_vehicle_lord():
    """Seaplane Mechanic gives Vehicles +0/+1 (when crewed = a creature)."""
    game, p1, _ = _make_game_with_two_players()
    _put_on_battlefield(game, p1, "Seaplane Mechanic", emit_etb=False)
    vehicle = game.create_object(
        name="Some Plane", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.ARTIFACT, CardType.CREATURE},
                                         subtypes={'Vehicle'},
                                         power=3, toughness=2, mana_cost=""),
        card_def=None,
    )
    t = get_toughness(vehicle, game.state)
    assert t == 3, f"Expected +0/+1, total 3; got {t}"
    print("PASSED: Seaplane Mechanic gives Vehicles +0/+1 (when crewed)")


# ----------------------------------------------------------------------------
# Spirit Protection keyword grant
# ----------------------------------------------------------------------------

def test_spirit_protection_grants_hexproof_to_spirits():
    game, p1, _ = _make_game_with_two_players()
    _put_on_battlefield(game, p1, "Spirit Protection", emit_etb=False)
    spirit = game.create_object(
        name="My Spirit", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(types={CardType.CREATURE},
                                         subtypes={'Spirit'},
                                         power=1, toughness=1, mana_cost=""),
        card_def=None,
    )
    from src.engine.types import InterceptorPriority
    granted: list[str] = []
    a_evt = Event(type=EventType.QUERY_ABILITIES,
                  payload={'object_id': spirit.id, 'granted': granted},
                  source=spirit.id)
    for itc in sorted(game.state.interceptors.values(), key=lambda i: i.timestamp):
        if itc.priority != InterceptorPriority.QUERY:
            continue
        try:
            if itc.filter(a_evt, game.state):
                res = itc.handler(a_evt, game.state)
                if res.transformed_event:
                    a_evt = res.transformed_event
        except Exception:
            continue
    granted_final = a_evt.payload.get('granted', [])
    assert 'hexproof' in granted_final, \
        f"Expected hexproof granted; got {granted_final}"
    print("PASSED: Spirit Protection grants hexproof to Spirits")


# ----------------------------------------------------------------------------
# Bathhouse Sanctuary upkeep
# ----------------------------------------------------------------------------

def test_bathhouse_sanctuary_upkeep_gains_per_spirit():
    game, p1, _ = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Bathhouse Sanctuary", emit_etb=False)
    for i in range(3):
        game.create_object(
            name=f"Spirit {i}", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(types={CardType.CREATURE},
                                             subtypes={'Spirit'},
                                             power=1, toughness=1, mana_cost=""),
            card_def=None,
        )
    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'player': p1.id},
        source=None,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    gains = [e for e in new if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) == 3
             and e.source == obj.id]
    assert gains, f"Expected +3 life (3 spirits); got {[(e.type.name, e.payload) for e in new]}"
    print("PASSED: Bathhouse Sanctuary upkeep gains 1 per Spirit")


# ----------------------------------------------------------------------------
# Curse Breaker resolve (multicolor instant)
# ----------------------------------------------------------------------------

def test_curse_breaker_resolve_gains_caster_and_drains_opp():
    game, p1, p2 = _make_game_with_two_players()
    game.state.active_player = p1.id
    p1_start = p1.life
    p2_start = p2.life
    events = studio_ghibli._curse_breaker_resolve([], game.state)
    for e in events:
        game.emit(e)
    assert p1.life >= p1_start + 2, f"Expected +2 to caster; got {p1.life - p1_start}"
    assert p2.life <= p2_start - 2, f"Expected -2 to opp; got {p2.life - p2_start}"
    print("PASSED: Curse Breaker gains caster 2 and drains opp 2")


# ----------------------------------------------------------------------------
# Bathhouse Specter combat damage discard
# ----------------------------------------------------------------------------

def test_bathhouse_specter_combat_damage_triggers_discard():
    game, p1, p2 = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Bathhouse Specter", emit_etb=False)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'source': obj.id, 'target': p2.id, 'amount': 2, 'is_combat': True},
        source=obj.id,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    discards = [e for e in new if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id]
    assert discards, f"Expected p2 discard; got {[e.type.name for e in new]}"
    print("PASSED: Bathhouse Specter combat damage triggers opp discard")


# ----------------------------------------------------------------------------
# Pre-existing real-implementation cards (regression sweep)
# ----------------------------------------------------------------------------

def test_chihiro_etb_emits_exile_event():
    game, p1, _ = _make_game_with_two_players()
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Chihiro, Spirited Child")
    new = game.state.event_log[before:]
    exiles = [e for e in new if e.type == EventType.EXILE and e.source == obj.id]
    assert exiles, f"Expected EXILE event from Chihiro; got {[e.type.name for e in new]}"
    print("PASSED: Chihiro ETB emits exile")


def test_witch_familiar_death_draw():
    game, p1, _ = _make_game_with_two_players()
    obj = _put_on_battlefield(game, p1, "Witch's Familiar", emit_etb=False)
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'battlefield',
            'to_zone': 'graveyard',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=obj.id,
        controller=p1.id,
    ))
    new = game.state.event_log[before:]
    draws = [e for e in new if e.type == EventType.DRAW]
    assert draws, f"Expected DRAW on Witch's Familiar death; got {[e.type.name for e in new]}"
    print("PASSED: Witch's Familiar draws on death")


def test_skipped_cards_at_least_load():
    """Cards we couldn't implement (engine gap) should still load."""
    game, p1, _ = _make_game_with_two_players()
    for card_name in SKIPPED_CARDS:
        if card_name not in STUDIO_GHIBLI_CARDS:
            continue
        _put_on_battlefield(game, p1, card_name, emit_etb=False)
    print(f"PASSED: {len(SKIPPED_CARDS)} skipped cards load without crashes")


TESTS = [
    test_corrupted_kodama_etb_drains_each_opp_and_gains_self,
    test_bathhouse_servant_etb_gains_2_life,
    test_valley_villager_etb_gains_2_life,
    test_catbus_etb_search_for_basic_land,
    test_wild_wolf_etb_search_for_wolf,
    test_sheeta_etb_creates_laputan_amulet,
    test_spirit_of_vengeance_death_drains_opp,
    test_baby_ohmu_death_searches_for_forest,
    test_toxic_jungle_lurker_death_puts_counters_on_opp_creatures,
    test_insect_swarm_grows_per_other_insect,
    test_ancient_tree_spirit_natures_wrath,
    test_dark_forest_creature_natures_wrath_power_only,
    test_jiji_witch_lord_buffs_other_witches,
    test_seaplane_mechanic_vehicle_lord,
    test_spirit_protection_grants_hexproof_to_spirits,
    test_bathhouse_sanctuary_upkeep_gains_per_spirit,
    test_curse_breaker_resolve_gains_caster_and_drains_opp,
    test_bathhouse_specter_combat_damage_triggers_discard,
    test_chihiro_etb_emits_exile_event,
    test_witch_familiar_death_draw,
    test_skipped_cards_at_least_load,
]


if __name__ == "__main__":
    print("=" * 60)
    print("Studio Ghibli interceptor verification suite")
    print("=" * 60)
    passed = 0
    failed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(TESTS)}")
    print("=" * 60)
    if failed:
        sys.exit(1)
