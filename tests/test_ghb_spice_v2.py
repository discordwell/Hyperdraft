"""
Studio Ghibli Spice Pass V2 Expansion Tests

Validates 7 high-depth build-around cards added on top of the Phase A
spice pass. Each card scores on >=3 axes (state coupling, decision
pressure, zone movement, asymmetry, synergy hook) to push GHB from
2/4 health gates to 3/4 or 4/4.

Mirrors test_studio_ghibli_spice.py shape (gotcha #18: worktree-portable
sys.path).
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.studio_ghibli import STUDIO_GHIBLI_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE."""
    card_def = STUDIO_GHIBLI_CARDS[card_name]
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


# ============================================================================
# Howl, Wandering Heart-Wizard — snowball + transform via heart counters
# ============================================================================

def test_howl_wandering_heart_loads():
    """Loads as Legendary Wizard with cast + end-step triggers + activated ability."""
    print("\n=== Howl Wandering Heart: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    howl = _put_on_battlefield(game, p1, "Howl, Wandering Heart-Wizard")
    chars = howl.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Wizard' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # Two interceptors: spell cast trigger + end step trigger.
    assert len(howl.interceptor_ids) >= 2
    # One activated ability.
    abilities = getattr(howl.state, 'activated_abilities', [])
    assert len(abilities) >= 1
    print(f"  Loaded with {len(howl.interceptor_ids)} interceptors, "
          f"{len(abilities)} activated abilities")


def test_howl_heart_counter_on_spell_cast():
    """Casting an instant/sorcery puts a heart counter on Howl."""
    print("\n=== Howl: heart counter on cast ===")
    game = Game()
    p1 = game.add_player("Alice")
    howl = _put_on_battlefield(game, p1, "Howl, Wandering Heart-Wizard")
    # Build a fake instant spell.
    spell = game.create_object(
        name="Test Bolt",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            colors={Color.RED},
        ),
    )
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'controller': p1.id,
            'spell_id': spell.id,
            'mana_value': 1,
        },
        controller=p1.id,
    ))
    hearts = howl.state.counters.get('heart', 0)
    assert hearts == 1, f"Expected 1 heart counter, got {hearts}"
    print(f"  Heart counters: {hearts}")


def test_howl_end_step_transform_at_5_hearts():
    """At 5+ heart counters, end step grants +3/+1 flying double_strike EOT."""
    print("\n=== Howl: end-step transform ===")
    game = Game()
    p1 = game.add_player("Alice")
    howl = _put_on_battlefield(game, p1, "Howl, Wandering Heart-Wizard")
    # Manually set 5 hearts.
    howl.state.counters['heart'] = 5
    game.state.active_player = p1.id
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'step': 'end_step',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    new = game.state.event_log[len(before_log):]
    pt_mods = [e for e in new
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('object_id') == howl.id
               and e.payload.get('power_mod') == 3]
    fly_grants = [e for e in new
                  if e.type == EventType.GRANT_KEYWORD
                  and e.payload.get('object_id') == howl.id
                  and e.payload.get('keyword') == 'flying']
    assert pt_mods, f"Expected +3/+1 PT_MODIFICATION at 5 hearts: {[e.type.name for e in new]}"
    assert fly_grants, "Expected flying grant"
    print(f"  Transformed at 5 hearts: +3/+1 flying granted")


def test_howl_no_transform_below_5_hearts():
    """Edge: below 5 hearts, end step does not transform."""
    print("\n=== Howl: no transform below threshold ===")
    game = Game()
    p1 = game.add_player("Alice")
    howl = _put_on_battlefield(game, p1, "Howl, Wandering Heart-Wizard")
    howl.state.counters['heart'] = 3
    game.state.active_player = p1.id
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'step': 'end_step',
                 'active_player': p1.id, 'turn_number': 1},
    ))
    new = game.state.event_log[len(before_log):]
    pt_mods = [e for e in new
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('object_id') == howl.id]
    assert not pt_mods, f"Should NOT transform below 5 hearts; got {pt_mods}"
    print(f"  No transform below 5 hearts (correct)")


# ============================================================================
# Yubaba, Bathhouse Greed — ETB curse + greed-death draw
# ============================================================================

def test_yubaba_bathhouse_greed_loads():
    """Loads as Legendary Witch with multiple interceptors."""
    print("\n=== Yubaba Bathhouse Greed: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    yu = _put_on_battlefield(game, p1, "Yubaba, Bathhouse Greed")
    chars = yu.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Witch' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(yu.interceptor_ids) >= 3
    print(f"  Loaded with {len(yu.interceptor_ids)} interceptors")


def test_yubaba_etb_places_greed_counters_on_opp_creature():
    """ETB: place greed counters on opp creature equal to opp hand size (max 3)."""
    print("\n=== Yubaba: ETB greed counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Bob has an opp creature on BF.
    bob_creat = game.create_object(
        name="Bob's Wolf",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            colors={Color.GREEN},
            power=3, toughness=3,
        ),
    )
    # Give Bob 2 cards in hand.
    for i in range(2):
        c = game.create_object(
            name=f"Bob's Card {i}",
            owner_id=p2.id,
            zone=ZoneType.HAND,
            characteristics=Characteristics(
                types={CardType.SORCERY},
                colors={Color.GREEN},
            ),
        )
    _put_on_battlefield(game, p1, "Yubaba, Bathhouse Greed")
    greed = bob_creat.state.counters.get('greed', 0)
    assert greed == 2, f"Expected 2 greed counters (hand size=2), got {greed}"
    print(f"  Opp creature has {greed} greed counters")


def test_yubaba_greed_death_draws_card():
    """When a creature with greed counters dies, draw a card."""
    print("\n=== Yubaba: greed death draws ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    yu = _put_on_battlefield(game, p1, "Yubaba, Bathhouse Greed")
    # Build greed-marked creature for opp.
    victim = game.create_object(
        name="Doomed Wolf",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    victim.state.counters['greed'] = 2
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': victim.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p2.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[len(before_log):]
    draws = [e for e in new if e.type == EventType.DRAW
             and e.source == yu.id
             and e.payload.get('player') == p1.id]
    assert draws, f"Expected DRAW on greed death: {[e.type.name for e in new]}"
    print(f"  Greed death triggered draw for Yubaba's controller")


def test_yubaba_no_draw_on_non_greed_death():
    """Edge: creature without greed counter dying does NOT draw."""
    print("\n=== Yubaba: non-greed death edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    yu = _put_on_battlefield(game, p1, "Yubaba, Bathhouse Greed")
    clean = game.create_object(
        name="Clean Wolf",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    # No greed counter on this one.
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': clean.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p2.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[len(before_log):]
    draws = [e for e in new if e.type == EventType.DRAW
             and e.source == yu.id]
    assert not draws, f"Should NOT draw on non-greed death; got {draws}"
    print(f"  No draw on non-greed death (correct)")


# ============================================================================
# No-Face, Devouring Spirit — feed-on-card-loss + activated drain
# ============================================================================

def test_no_face_devouring_loads():
    """Loads as Legendary Spirit with feed trigger + keyword grants + activated."""
    print("\n=== No-Face Devouring: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    nf = _put_on_battlefield(game, p1, "No-Face, Devouring Spirit")
    chars = nf.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Spirit' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # 4 interceptors: feed + 3 keyword grants.
    assert len(nf.interceptor_ids) >= 4
    abilities = getattr(nf.state, 'activated_abilities', [])
    assert len(abilities) >= 1
    print(f"  {len(nf.interceptor_ids)} interceptors, {len(abilities)} activated")


def test_no_face_feeds_on_opp_card_to_gy():
    """When opp's card goes from hand to GY, put hunger counter on No-Face."""
    print("\n=== No-Face: feed on discard ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    nf = _put_on_battlefield(game, p1, "No-Face, Devouring Spirit")
    # Bob's card in hand → graveyard.
    bob_card = game.create_object(
        name="Bob's Discard",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            colors={Color.RED},
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': bob_card.id,
            'from_zone': f'hand_{p2.id}',
            'from_zone_type': ZoneType.HAND,
            'to_zone': f'graveyard_{p2.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    hunger = nf.state.counters.get('hunger', 0)
    assert hunger == 1, f"Expected 1 hunger counter, got {hunger}"
    print(f"  Hunger counters: {hunger}")


def test_no_face_menace_at_3_hunger():
    """At 3+ hunger counters, No-Face has menace."""
    print("\n=== No-Face: menace at 3 hunger ===")
    game = Game()
    p1 = game.add_player("Alice")
    nf = _put_on_battlefield(game, p1, "No-Face, Devouring Spirit")
    nf.state.counters['hunger'] = 3
    assert has_ability(nf, 'menace', game.state), "Expected menace at 3 hunger"
    print(f"  Menace granted at 3 hunger")


def test_no_face_no_keywords_below_threshold():
    """Edge: at 2 hunger counters, no menace/deathtouch."""
    print("\n=== No-Face: no keywords below threshold ===")
    game = Game()
    p1 = game.add_player("Alice")
    nf = _put_on_battlefield(game, p1, "No-Face, Devouring Spirit")
    nf.state.counters['hunger'] = 2
    assert not has_ability(nf, 'menace', game.state)
    assert not has_ability(nf, 'deathtouch', game.state)
    print(f"  No keywords below threshold (correct)")


def test_no_face_does_not_feed_on_own_loss():
    """Edge: controller's own card loss does NOT feed No-Face."""
    print("\n=== No-Face: own loss edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    nf = _put_on_battlefield(game, p1, "No-Face, Devouring Spirit")
    my_card = game.create_object(
        name="My Card",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            colors={Color.GREEN},
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': my_card.id,
            'from_zone': f'hand_{p1.id}',
            'from_zone_type': ZoneType.HAND,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    hunger = nf.state.counters.get('hunger', 0)
    assert hunger == 0, f"Should not feed on own loss; got {hunger}"
    print(f"  Did not feed on own loss (correct)")


# ============================================================================
# The Spirit-Realm Summoning — Saga with tribal Spirit payoff
# ============================================================================

def test_spirit_realm_summoning_loads_as_saga():
    """Loads as Saga Enchantment with chapter interceptors."""
    print("\n=== Spirit-Realm Summoning: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Spirit-Realm Summoning")
    chars = saga.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in chars.subtypes
    # Saga should register multiple interceptors.
    assert len(saga.interceptor_ids) >= 2
    print(f"  Loaded with {len(saga.interceptor_ids)} interceptors")


def test_spirit_realm_summoning_chapter_ii_creates_spirit_token():
    """Chapter II creates a 2/2 green Spirit token with vigilance."""
    print("\n=== Spirit-Realm Summoning: chapter II ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Spirit-Realm Summoning")
    # Directly invoke chapter II handler.
    from src.cards.custom.studio_ghibli import _spirit_realm_summoning_ch_ii
    events = _spirit_realm_summoning_ch_ii(saga, game.state)
    create_tokens = [e for e in events if e.type == EventType.CREATE_TOKEN]
    assert create_tokens, "Expected CREATE_TOKEN from chapter II"
    tok = create_tokens[0].payload.get('token') or {}
    assert tok.get('name') == 'Forest Spirit'
    assert tok.get('power') == 2
    assert 'Spirit' in (tok.get('subtypes') or set())
    print(f"  Chapter II creates 2/2 Spirit token")


def test_spirit_realm_summoning_chapter_iii_pumps_spirits():
    """Chapter III: Spirits you control get +1/+1 and flying."""
    print("\n=== Spirit-Realm Summoning: chapter III ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Spirit-Realm Summoning")
    # Build a spirit and a non-spirit and an opp spirit.
    my_spirit = game.create_object(
        name="My Spirit",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Spirit"},
            power=1, toughness=1,
        ),
    )
    my_nonspirit = game.create_object(
        name="My Human",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            power=1, toughness=1,
        ),
    )
    opp_spirit = game.create_object(
        name="Opp Spirit",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Spirit"},
            power=1, toughness=1,
        ),
    )
    from src.cards.custom.studio_ghibli import _spirit_realm_summoning_ch_iii
    events = _spirit_realm_summoning_ch_iii(saga, game.state)
    pt_ids = {e.payload.get('object_id') for e in events
              if e.type == EventType.PT_MODIFICATION}
    assert my_spirit.id in pt_ids, "My Spirit should be pumped"
    assert my_nonspirit.id not in pt_ids, "Non-spirit should NOT be pumped"
    assert opp_spirit.id not in pt_ids, "Opp spirit should NOT be pumped"
    print(f"  Chapter III correctly targets only your Spirits")


# ============================================================================
# Princess Mononoke's Curse — Saga with curse counter scaling
# ============================================================================

def test_mononoke_curse_loads_as_saga():
    """Loads as Saga Enchantment."""
    print("\n=== Mononoke's Curse: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Princess Mononoke's Curse")
    chars = saga.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in chars.subtypes
    assert len(saga.interceptor_ids) >= 2
    print(f"  Loaded with {len(saga.interceptor_ids)} interceptors")


def test_mononoke_curse_chapter_i_drains_and_curses():
    """Chapter I: each opponent loses 2 life; put curse on a creature you control."""
    print("\n=== Mononoke's Curse: chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "Princess Mononoke's Curse")
    # Give p1 a creature to receive the curse.
    mine = game.create_object(
        name="Forest Wolf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=3, toughness=3,
        ),
    )
    from src.cards.custom.studio_ghibli import _mononoke_curse_ch_i
    events = _mononoke_curse_ch_i(saga, game.state)
    life_drains = [e for e in events if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('player') == p2.id
                   and e.payload.get('amount') == -2]
    curses = [e for e in events if e.type == EventType.COUNTER_ADDED
              and e.payload.get('counter_type') == 'curse']
    assert life_drains, "Expected -2 life for opp"
    assert curses, "Expected curse counter on a creature"
    assert curses[0].payload.get('object_id') == mine.id
    print(f"  Chapter I drains opp + curses biggest friendly")


def test_mononoke_curse_chapter_iii_scales_with_curses():
    """Chapter III: cursed creature gets +X/+X where X = curse counters on it."""
    print("\n=== Mononoke's Curse: chapter III scaling ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Princess Mononoke's Curse")
    cursed = game.create_object(
        name="Doomed Wolf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    cursed.state.counters['curse'] = 3
    uncursed = game.create_object(
        name="Plain Wolf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    from src.cards.custom.studio_ghibli import _mononoke_curse_ch_iii
    events = _mononoke_curse_ch_iii(saga, game.state)
    pt_for_cursed = [e for e in events
                     if e.type == EventType.PT_MODIFICATION
                     and e.payload.get('object_id') == cursed.id]
    pt_for_uncursed = [e for e in events
                       if e.type == EventType.PT_MODIFICATION
                       and e.payload.get('object_id') == uncursed.id]
    assert pt_for_cursed, "Cursed creature should be pumped"
    assert pt_for_cursed[0].payload.get('power_mod') == 3
    assert pt_for_cursed[0].payload.get('toughness_mod') == 3
    assert not pt_for_uncursed, "Uncursed creature should not be pumped"
    print(f"  Chapter III: +3/+3 to cursed, no effect on uncursed")


# ============================================================================
# San, Wolf-Sister Ascendant — modal ETB tribal
# ============================================================================

def test_san_ascendant_loads():
    """Loads as Legendary Human/Warrior with ETB + ward."""
    print("\n=== San Ascendant: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    san = _put_on_battlefield(game, p1, "San, Wolf-Sister Ascendant")
    chars = san.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Human' in chars.subtypes
    assert 'Warrior' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # ETB trigger + ward replacement = 2+ interceptors.
    assert len(san.interceptor_ids) >= 2
    print(f"  Loaded with {len(san.interceptor_ids)} interceptors")


def test_san_ascendant_etb_pumps_wolves_when_2_plus():
    """When 2+ Wolves on BF, ETB picks Mode B: pump all Wolves +2/+0."""
    print("\n=== San: Mode B pump (2+ wolves) ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Build 2 wolves first.
    wolves = []
    for i in range(2):
        w = game.create_object(
            name=f"Wolf {i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE},
                subtypes={"Wolf"},
                power=2, toughness=2,
            ),
        )
        wolves.append(w)
    before_log = list(game.state.event_log)
    _put_on_battlefield(game, p1, "San, Wolf-Sister Ascendant")
    new = game.state.event_log[len(before_log):]
    pt_mods = [e for e in new
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('power_mod') == 2]
    pumped_ids = {e.payload.get('object_id') for e in pt_mods}
    assert wolves[0].id in pumped_ids and wolves[1].id in pumped_ids, (
        f"Both wolves should be pumped, pumped={pumped_ids}, "
        f"wolf ids={[w.id for w in wolves]}"
    )
    print(f"  Mode B chosen: {len(pumped_ids)} wolves pumped")


def test_san_ascendant_etb_tutors_when_no_wolves():
    """When no Wolves and no opp creatures, ETB picks Mode C: tutor a Wolf."""
    print("\n=== San: Mode C tutor (default) ===")
    game = Game()
    p1 = game.add_player("Alice")
    before_log = list(game.state.event_log)
    _put_on_battlefield(game, p1, "San, Wolf-Sister Ascendant")
    new = game.state.event_log[len(before_log):]
    searches = [e for e in new
                if e.type == EventType.SEARCH_LIBRARY
                and e.payload.get('subtype') == 'Wolf']
    assert searches, f"Expected SEARCH_LIBRARY for Wolf: {[e.type.name for e in new]}"
    print(f"  Mode C tutor: search for Wolf emitted")


# ============================================================================
# Chihiro, Bridge Between Worlds — opp-hand-loss snowball + scaling tutor
# ============================================================================

def test_chihiro_bridge_loads():
    """Loads as Legendary Human/Advisor with trigger + activated ability."""
    print("\n=== Chihiro Bridge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    chi = _put_on_battlefield(game, p1, "Chihiro, Bridge Between Worlds")
    chars = chi.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Advisor' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(chi.interceptor_ids) >= 1
    abilities = getattr(chi.state, 'activated_abilities', [])
    assert len(abilities) >= 1
    print(f"  {len(chi.interceptor_ids)} interceptors, {len(abilities)} activated")


def test_chihiro_bridge_counters_opp_hand_loss():
    """When opp card leaves hand to GY, put name counter on Chihiro and scry."""
    print("\n=== Chihiro: name counter on opp hand loss ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    chi = _put_on_battlefield(game, p1, "Chihiro, Bridge Between Worlds")
    bob_card = game.create_object(
        name="Bob's Discard",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            colors={Color.RED},
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': bob_card.id,
            'from_zone': f'hand_{p2.id}',
            'from_zone_type': ZoneType.HAND,
            'to_zone': f'graveyard_{p2.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    names = chi.state.counters.get('name', 0)
    assert names == 1, f"Expected 1 name counter, got {names}"
    # Should also have scry'd.
    scrys = [e for e in game.state.event_log
             if e.type == EventType.SCRY and e.source == chi.id]
    assert scrys, f"Expected scry"
    print(f"  Name counters: {names}, scry triggered")


def test_chihiro_bridge_no_counter_on_own_hand_loss():
    """Edge: controller's hand loss does NOT trigger."""
    print("\n=== Chihiro: own hand loss edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    chi = _put_on_battlefield(game, p1, "Chihiro, Bridge Between Worlds")
    my_card = game.create_object(
        name="My Card",
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            colors={Color.WHITE},
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': my_card.id,
            'from_zone': f'hand_{p1.id}',
            'from_zone_type': ZoneType.HAND,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    names = chi.state.counters.get('name', 0)
    assert names == 0, f"Should NOT count own hand loss; got {names}"
    print(f"  Did not count own hand loss (correct)")


def test_chihiro_bridge_no_counter_when_going_to_battlefield():
    """Edge: opp card going from hand → BF (a normal cast) does NOT trigger."""
    print("\n=== Chihiro: hand → BF edge (normal cast) ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    chi = _put_on_battlefield(game, p1, "Chihiro, Bridge Between Worlds")
    bob_creature = game.create_object(
        name="Bob's Creature",
        owner_id=p2.id,
        zone=ZoneType.HAND,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': bob_creature.id,
            'from_zone': f'hand_{p2.id}',
            'from_zone_type': ZoneType.HAND,
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    names = chi.state.counters.get('name', 0)
    assert names == 0, f"Should NOT trigger on hand→BF cast; got {names}"
    print(f"  Hand→BF does not trigger (correct)")


# ============================================================================
# Registry smoke test
# ============================================================================

def test_all_v2_spice_cards_register():
    """All 7 v2 spice cards in registry."""
    print("\n=== V2 Registry smoke ===")
    expected = [
        "Howl, Wandering Heart-Wizard",
        "Yubaba, Bathhouse Greed",
        "No-Face, Devouring Spirit",
        "The Spirit-Realm Summoning",
        "Princess Mononoke's Curse",
        "San, Wolf-Sister Ascendant",
        "Chihiro, Bridge Between Worlds",
    ]
    for name in expected:
        assert name in STUDIO_GHIBLI_CARDS, f"Missing in registry: {name}"
    print(f"  All {len(expected)} v2 spice cards present")


if __name__ == "__main__":
    test_howl_wandering_heart_loads()
    test_howl_heart_counter_on_spell_cast()
    test_howl_end_step_transform_at_5_hearts()
    test_howl_no_transform_below_5_hearts()
    test_yubaba_bathhouse_greed_loads()
    test_yubaba_etb_places_greed_counters_on_opp_creature()
    test_yubaba_greed_death_draws_card()
    test_yubaba_no_draw_on_non_greed_death()
    test_no_face_devouring_loads()
    test_no_face_feeds_on_opp_card_to_gy()
    test_no_face_menace_at_3_hunger()
    test_no_face_no_keywords_below_threshold()
    test_no_face_does_not_feed_on_own_loss()
    test_spirit_realm_summoning_loads_as_saga()
    test_spirit_realm_summoning_chapter_ii_creates_spirit_token()
    test_spirit_realm_summoning_chapter_iii_pumps_spirits()
    test_mononoke_curse_loads_as_saga()
    test_mononoke_curse_chapter_i_drains_and_curses()
    test_mononoke_curse_chapter_iii_scales_with_curses()
    test_san_ascendant_loads()
    test_san_ascendant_etb_pumps_wolves_when_2_plus()
    test_san_ascendant_etb_tutors_when_no_wolves()
    test_chihiro_bridge_loads()
    test_chihiro_bridge_counters_opp_hand_loss()
    test_chihiro_bridge_no_counter_on_own_hand_loss()
    test_chihiro_bridge_no_counter_when_going_to_battlefield()
    test_all_v2_spice_cards_register()
    print("\n" + "=" * 60)
    print("ALL STUDIO GHIBLI V2 SPICE TESTS PASSED!")
    print("=" * 60)
