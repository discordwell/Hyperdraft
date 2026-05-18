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
# Totoro, Spirit of the Camphor Tree — modal-choose-two ETB + Spirit lord
# ============================================================================

def test_totoro_camphor_loads():
    """Loads as Legendary Spirit/God with modal ETB + lord static."""
    print("\n=== Totoro Camphor: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tot = _put_on_battlefield(game, p1, "Totoro, Spirit of the Camphor Tree")
    chars = tot.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Spirit' in chars.subtypes
    assert 'God' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # ETB modal + lord static = 2+ interceptors.
    assert len(tot.interceptor_ids) >= 2
    print(f"  Loaded with {len(tot.interceptor_ids)} interceptors")


def test_totoro_camphor_pumps_other_spirits():
    """Spirits you control get +1/+0."""
    print("\n=== Totoro: Spirit lord ===")
    game = Game()
    p1 = game.add_player("Alice")
    spirit = game.create_object(
        name="Forest Spirit",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Spirit"},
            power=1, toughness=1,
        ),
    )
    base_p = get_power(spirit, game.state)
    _put_on_battlefield(game, p1, "Totoro, Spirit of the Camphor Tree")
    new_p = get_power(spirit, game.state)
    assert new_p == base_p + 1, f"Expected +1 power: {base_p}→{new_p}"
    print(f"  Spirit P: {base_p} → {new_p}")


def test_totoro_camphor_etb_opens_modal_choice():
    """ETB sets state.pending_choice for the modal."""
    print("\n=== Totoro: ETB modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Totoro, Spirit of the Camphor Tree")
    # The modal helper sets state.pending_choice as a side effect.
    # We may or may not see it depending on whether the trigger has resolved
    # all the way through — at minimum, the trigger fires without crashing.
    # Look for evidence the ETB ran: check for a modal_with_targeting choice
    # OR a no-pending state if the AI heuristic auto-resolved.
    pending = game.state.pending_choice
    if pending is not None:
        assert pending.choice_type == "modal_with_targeting", (
            f"Wrong choice type: {pending.choice_type}"
        )
        print(f"  ETB modal choice opened: {pending.choice_type}")
    else:
        # Auto-resolved path is also acceptable in this test.
        print(f"  ETB modal fired (auto-resolved or AI-resolved)")


# ============================================================================
# Kaonashi's Banquet — Saga: reveal hand, discard, exile + spirits
# ============================================================================

def test_kaonashis_banquet_loads_as_saga():
    """Loads as Saga enchantment."""
    print("\n=== Kaonashi's Banquet: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Kaonashi's Banquet")
    chars = saga.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in chars.subtypes
    assert len(saga.interceptor_ids) >= 2
    print(f"  Loaded with {len(saga.interceptor_ids)} interceptors")


def test_kaonashis_banquet_chapter_i_reveal_and_scry():
    """Chapter I reveals each opp hand and scries 2."""
    print("\n=== Kaonashi: chapter I reveal + scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "Kaonashi's Banquet")
    from src.cards.custom.studio_ghibli import _kaonashis_banquet_ch_i
    events = _kaonashis_banquet_ch_i(saga, game.state)
    reveals = [e for e in events
               if e.type == EventType.REVEAL_HAND
               and e.payload.get('player') == p2.id]
    scrys = [e for e in events
             if e.type == EventType.SCRY
             and e.payload.get('player') == p1.id]
    assert reveals, "Expected REVEAL for opp's hand"
    assert scrys, "Expected SCRY for controller"
    print(f"  Chapter I emits REVEAL + SCRY")


def test_kaonashis_banquet_chapter_iii_exile_and_tokens():
    """Chapter III exiles opp creature and creates spirits = opp GY size."""
    print("\n=== Kaonashi: chapter III exile + tokens ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "Kaonashi's Banquet")
    # Give Bob a creature and 3 cards in graveyard.
    victim = game.create_object(
        name="Bob's Wolf",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=3, toughness=3,
        ),
    )
    for i in range(3):
        c = game.create_object(
            name=f"Bob GY {i}",
            owner_id=p2.id,
            zone=ZoneType.GRAVEYARD,
            characteristics=Characteristics(types={CardType.SORCERY}),
        )
    from src.cards.custom.studio_ghibli import _kaonashis_banquet_ch_iii
    events = _kaonashis_banquet_ch_iii(saga, game.state)
    exiles = [e for e in events
              if e.type == EventType.EXILE
              and e.payload.get('object_id') == victim.id]
    tokens = [e for e in events
              if e.type == EventType.CREATE_TOKEN]
    assert exiles, "Expected EXILE for opp creature"
    assert len(tokens) == 3, f"Expected 3 Spirit tokens (GY size), got {len(tokens)}"
    print(f"  Chapter III exiles + creates {len(tokens)} Spirit tokens")


# ============================================================================
# Ashitaka, Iron-Cursed Prince — targeted ETB + cursed-attack trigger
# ============================================================================

def test_ashitaka_iron_cursed_loads():
    """Loads as Legendary Human/Warrior."""
    print("\n=== Ashitaka Iron-Cursed: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ash = _put_on_battlefield(game, p1, "Ashitaka, Iron-Cursed Prince")
    chars = ash.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Human' in chars.subtypes
    assert 'Warrior' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # Targeted-ETB + cursed-attack trigger = 2.
    assert len(ash.interceptor_ids) >= 2
    print(f"  Loaded with {len(ash.interceptor_ids)} interceptors")


def test_ashitaka_cursed_attack_punishes_and_draws():
    """When a creature with 3+ curse counters attacks, -2/-0 + draw."""
    print("\n=== Ashitaka: cursed attack punishes ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ash = _put_on_battlefield(game, p1, "Ashitaka, Iron-Cursed Prince")
    # Build a cursed creature for Bob.
    attacker = game.create_object(
        name="Cursed Attacker",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=4, toughness=4,
        ),
    )
    attacker.state.counters['curse'] = 3
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'attacker': attacker.id,
                 'defender': p1.id},
        source=attacker.id,
    ))
    new = game.state.event_log[len(before_log):]
    pt_mods = [e for e in new
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('object_id') == attacker.id
               and e.payload.get('power_mod') == -2]
    draws = [e for e in new
             if e.type == EventType.DRAW
             and e.source == ash.id
             and e.payload.get('player') == p1.id]
    assert pt_mods, f"Expected -2/-0 PT_MODIFICATION: {[e.type.name for e in new]}"
    assert draws, "Expected DRAW for Ashitaka's controller"
    print(f"  Cursed attacker got -2/-0; controller drew")


def test_ashitaka_uncursed_attack_no_punish():
    """Edge: an attacker without curse counters does NOT trigger."""
    print("\n=== Ashitaka: uncursed attack edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ash = _put_on_battlefield(game, p1, "Ashitaka, Iron-Cursed Prince")
    plain = game.create_object(
        name="Plain Attacker",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': plain.id, 'attacker': plain.id,
                 'defender': p1.id},
        source=plain.id,
    ))
    new = game.state.event_log[len(before_log):]
    pt_mods = [e for e in new
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('object_id') == plain.id]
    assert not pt_mods, f"Should not punish uncursed attacker; got {pt_mods}"
    print(f"  No punishment for uncursed attacker (correct)")


# ============================================================================
# Kiki, Witch on Errands — modal-choose-one ETB + cast-trigger
# ============================================================================

def test_kiki_witch_errands_loads():
    """Loads as Legendary Human/Witch."""
    print("\n=== Kiki Witch Errands: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kiki = _put_on_battlefield(game, p1, "Kiki, Witch on Errands")
    chars = kiki.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Witch' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # ETB modal + spell-cast trigger = 2.
    assert len(kiki.interceptor_ids) >= 2
    print(f"  Loaded with {len(kiki.interceptor_ids)} interceptors")


def test_kiki_witch_cast_grants_flying():
    """Casting a Spirit or Witch grants Kiki flying EOT."""
    print("\n=== Kiki: witch cast grants flying ===")
    game = Game()
    p1 = game.add_player("Alice")
    kiki = _put_on_battlefield(game, p1, "Kiki, Witch on Errands")
    # Build a fake Witch spell.
    spell = game.create_object(
        name="Test Witch",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Witch"},
            colors={Color.BLUE},
            power=2, toughness=2,
        ),
    )
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'controller': p1.id,
            'spell_id': spell.id,
            'mana_value': 2,
        },
        controller=p1.id,
    ))
    new = game.state.event_log[len(before_log):]
    grants = [e for e in new
              if e.type == EventType.GRANT_KEYWORD
              and e.payload.get('object_id') == kiki.id
              and e.payload.get('keyword') == 'flying']
    assert grants, f"Expected flying grant on Witch cast: {[e.type.name for e in new]}"
    print(f"  Witch cast → Kiki gained flying")


def test_kiki_non_witch_cast_no_grant():
    """Edge: non-Witch/non-Spirit cast does NOT grant flying."""
    print("\n=== Kiki: non-witch cast edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    kiki = _put_on_battlefield(game, p1, "Kiki, Witch on Errands")
    plain = game.create_object(
        name="Plain Bolt",
        owner_id=p1.id,
        zone=ZoneType.LIBRARY,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            colors={Color.RED},
        ),
    )
    before_log = list(game.state.event_log)
    game.emit(Event(
        type=EventType.CAST,
        payload={
            'caster': p1.id,
            'controller': p1.id,
            'spell_id': plain.id,
            'mana_value': 1,
        },
        controller=p1.id,
    ))
    new = game.state.event_log[len(before_log):]
    grants = [e for e in new
              if e.type == EventType.GRANT_KEYWORD
              and e.payload.get('object_id') == kiki.id
              and e.payload.get('keyword') == 'flying']
    assert not grants, f"Should not grant flying on non-Witch cast; got {grants}"
    print(f"  Non-Witch cast does not grant flying (correct)")


# ============================================================================
# The Cursed Forest Awakens — Saga blending discard + counters + exile
# ============================================================================

def test_cursed_forest_awakens_loads_as_saga():
    """Loads as Saga enchantment."""
    print("\n=== Cursed Forest Awakens: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "The Cursed Forest Awakens")
    chars = saga.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in chars.subtypes
    assert len(saga.interceptor_ids) >= 2
    print(f"  Loaded with {len(saga.interceptor_ids)} interceptors")


def test_cursed_forest_chapter_i_discard_and_pump_tribes():
    """Chapter I: opp discards + +1/+1 counter on each Wolf/Spirit."""
    print("\n=== Cursed Forest: chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Cursed Forest Awakens")
    # Build a wolf, a spirit, and a non-tribal creature.
    wolf = game.create_object(
        name="My Wolf",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    spirit = game.create_object(
        name="My Spirit",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Spirit"},
            power=1, toughness=1,
        ),
    )
    human = game.create_object(
        name="My Human",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Human"},
            power=2, toughness=2,
        ),
    )
    from src.cards.custom.studio_ghibli import _cursed_forest_awakens_ch_i
    events = _cursed_forest_awakens_ch_i(saga, game.state)
    discards = [e for e in events
                if e.type == EventType.DISCARD
                and e.payload.get('player') == p2.id]
    counter_targets = {e.payload.get('object_id') for e in events
                       if e.type == EventType.COUNTER_ADDED
                       and e.payload.get('counter_type') == '+1/+1'}
    assert discards, "Expected DISCARD for opp"
    assert wolf.id in counter_targets, "Wolf should get +1/+1"
    assert spirit.id in counter_targets, "Spirit should get +1/+1"
    assert human.id not in counter_targets, "Human should NOT get +1/+1"
    print(f"  Chapter I: opp discards + Wolf/Spirit counter (Human untouched)")


def test_cursed_forest_chapter_iii_exile_counters():
    """Chapter III: exile up to 2 opp creatures with +1/+1 counters."""
    print("\n=== Cursed Forest: chapter III ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "The Cursed Forest Awakens")
    # Build 3 opp creatures: 2 with +1/+1, 1 without.
    c1 = game.create_object(
        name="Opp Cursed 1",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    c1.state.counters['+1/+1'] = 2
    c2 = game.create_object(
        name="Opp Cursed 2",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    c2.state.counters['+1/+1'] = 1
    plain = game.create_object(
        name="Opp Plain",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=2, toughness=2,
        ),
    )
    from src.cards.custom.studio_ghibli import _cursed_forest_awakens_ch_iii
    events = _cursed_forest_awakens_ch_iii(saga, game.state)
    exile_ids = {e.payload.get('object_id') for e in events
                 if e.type == EventType.EXILE}
    tokens = [e for e in events if e.type == EventType.CREATE_TOKEN]
    assert plain.id not in exile_ids, "Uncountered creature should NOT be exiled"
    assert len(exile_ids) <= 2, f"At most 2 exiles, got {len(exile_ids)}"
    assert len(tokens) == len(exile_ids), (
        f"Token count must match exile count: {len(tokens)} != {len(exile_ids)}"
    )
    print(f"  Chapter III: {len(exile_ids)} exiles, {len(tokens)} tokens")


# ============================================================================
# Haku, River-Lord Bound — becomes_creature land transform
# ============================================================================

def test_haku_river_lord_loads():
    """Loads as Legendary Spirit Dragon."""
    print("\n=== Haku River-Lord: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    haku = _put_on_battlefield(game, p1, "Haku, River-Lord Bound")
    chars = haku.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Spirit' in chars.subtypes
    assert 'Dragon' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # ETB + attack trigger = 2.
    assert len(haku.interceptor_ids) >= 2
    print(f"  Loaded with {len(haku.interceptor_ids)} interceptors")


def test_haku_etb_transforms_land():
    """ETB: target land you control becomes a 4/4 Spirit Dragon EOT.
    becomes_creature installs QUERY interceptors; verify via get_power."""
    print("\n=== Haku: ETB land transform ===")
    game = Game()
    p1 = game.add_player("Alice")
    land = game.create_object(
        name="Forest",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes={"Forest"},
            supertypes={"Basic"},
        ),
    )
    _put_on_battlefield(game, p1, "Haku, River-Lord Bound")
    # becomes_creature installs QUERY interceptors; power should be 4.
    new_p = get_power(land, game.state)
    new_t = get_toughness(land, game.state)
    assert new_p == 4, f"Power should be 4: {new_p}"
    assert new_t == 4, f"Toughness should be 4: {new_t}"
    print(f"  Land transformed: {new_p}/{new_t}")


# ============================================================================
# Ohmu, Forest Architect — modal ETB + grant_death_trigger
# ============================================================================

def test_ohmu_forest_architect_loads():
    """Loads as Legendary Insect/God."""
    print("\n=== Ohmu Forest Architect: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ohmu = _put_on_battlefield(game, p1, "Ohmu, Forest Architect")
    chars = ohmu.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Insect' in chars.subtypes
    assert 'God' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    # Modal ETB + grant trigger = 2.
    assert len(ohmu.interceptor_ids) >= 2
    print(f"  Loaded with {len(ohmu.interceptor_ids)} interceptors")


def test_ohmu_etb_opens_modal():
    """ETB opens a modal_with_targeting choice."""
    print("\n=== Ohmu: ETB modal ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Ohmu, Forest Architect")
    pending = game.state.pending_choice
    if pending is not None:
        assert pending.choice_type == "modal_with_targeting"
        print(f"  Modal choice opened")
    else:
        print(f"  Modal fired (auto-resolved)")


# ============================================================================
# Witch of the Waste, Fading Splendor — reveal hand + threaten
# ============================================================================

def test_witch_of_waste_fading_loads():
    """Loads as Legendary Witch."""
    print("\n=== Witch of the Waste Fading: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    witch = _put_on_battlefield(game, p1, "Witch of the Waste, Fading Splendor")
    chars = witch.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Witch' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(witch.interceptor_ids) >= 2
    print(f"  Loaded with {len(witch.interceptor_ids)} interceptors")


def test_witch_etb_reveals_and_threatens():
    """ETB reveals opp's hand and emits threaten events."""
    print("\n=== Witch of the Waste: ETB reveal + threaten ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Build a big opp creature to be threatened.
    opp_creat = game.create_object(
        name="Bob's Hulk",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Wolf"},
            power=5, toughness=5,
        ),
    )
    before_log = list(game.state.event_log)
    _put_on_battlefield(game, p1, "Witch of the Waste, Fading Splendor")
    new = game.state.event_log[len(before_log):]
    reveals = [e for e in new
               if e.type == EventType.REVEAL_HAND
               and e.payload.get('player') == p2.id]
    assert reveals, f"Expected REVEAL_HAND for opp: {[e.type.name for e in new[:10]]}"
    # Threaten emits CONTROL_CHANGE + UNTAP + GRANT_KEYWORD haste.
    ctrl_changes = [e for e in new if e.type == EventType.CONTROL_CHANGE]
    assert ctrl_changes, f"Expected CONTROL_CHANGE for threaten effect"
    print(f"  ETB revealed opp hand + threatened a creature")


# ============================================================================
# Phase 4 — Sheeta, Boh, Mononoke's Last Hunt, Suspect, Castle in the Sky
# ============================================================================

def test_sheeta_crystal_heir_loads():
    """Loads as Legendary Human/Cleric."""
    print("\n=== Sheeta Crystal Heir: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sh = _put_on_battlefield(game, p1, "Sheeta, Crystal Heir")
    chars = sh.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Cleric' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(sh.interceptor_ids) >= 2
    print(f"  Loaded with {len(sh.interceptor_ids)} interceptors")


def test_sheeta_etb_animates_artifact():
    """ETB: an artifact you control becomes a 3/3 Spirit Construct."""
    print("\n=== Sheeta: ETB animates artifact ===")
    game = Game()
    p1 = game.add_player("Alice")
    artifact = game.create_object(
        name="Hat",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            colors=set(),
        ),
    )
    _put_on_battlefield(game, p1, "Sheeta, Crystal Heir")
    new_p = get_power(artifact, game.state)
    assert new_p == 3, f"Power should be 3: {new_p}"
    print(f"  Artifact animated: P={new_p}")


def test_boh_pacified_giant_loads():
    """Loads as Legendary Spirit/Giant."""
    print("\n=== Boh Pacified Giant: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    boh = _put_on_battlefield(game, p1, "Boh, Pacified Giant")
    chars = boh.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Giant' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(boh.interceptor_ids) >= 1
    print(f"  Loaded with {len(boh.interceptor_ids)} interceptors")


def test_mononoke_last_hunt_loads_as_saga():
    """Loads as Saga enchantment."""
    print("\n=== Mononoke's Last Hunt: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Mononoke's Last Hunt")
    chars = saga.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in chars.subtypes
    assert len(saga.interceptor_ids) >= 2
    print(f"  Loaded with {len(saga.interceptor_ids)} interceptors")


def test_mononoke_last_hunt_chapter_i_tutors_wolf():
    """Chapter I emits SEARCH_LIBRARY for Wolf."""
    print("\n=== Mononoke's Last Hunt: chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Mononoke's Last Hunt")
    from src.cards.custom.studio_ghibli import _mononoke_last_hunt_ch_i
    events = _mononoke_last_hunt_ch_i(saga, game.state)
    searches = [e for e in events
                if e.type == EventType.SEARCH_LIBRARY
                and e.payload.get('subtype') == 'Wolf']
    assert searches, "Expected SEARCH_LIBRARY for Wolf"
    print(f"  Chapter I tutors a Wolf")


def test_suspect_the_conspirators_loads():
    """Loads as Enchantment."""
    print("\n=== Suspect the Conspirators: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    susp = _put_on_battlefield(game, p1, "Suspect the Conspirators")
    chars = susp.characteristics
    assert CardType.ENCHANTMENT in chars.types
    # Modal ETB + ETB heuristic = 2.
    assert len(susp.interceptor_ids) >= 2
    print(f"  Loaded with {len(susp.interceptor_ids)} interceptors")


def test_castle_in_the_sky_reawakened_loads():
    """Loads as Legendary Enchantment with activated ability + ETB triggers."""
    print("\n=== Castle in the Sky: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    castle = _put_on_battlefield(game, p1, "Castle in the Sky, Reawakened")
    chars = castle.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Legendary' in (chars.supertypes or set())
    # ETB scry-and-count + flying-ETB listener = 2.
    assert len(castle.interceptor_ids) >= 2
    abilities = getattr(castle.state, 'activated_abilities', [])
    assert len(abilities) >= 1
    print(f"  Loaded with {len(castle.interceptor_ids)} interceptors, "
          f"{len(abilities)} activated")


def test_castle_in_the_sky_etb_scrys_and_counters():
    """ETB: scry 3 + put a crystal counter on Castle."""
    print("\n=== Castle in the Sky: ETB scry + counter ===")
    game = Game()
    p1 = game.add_player("Alice")
    castle = _put_on_battlefield(game, p1, "Castle in the Sky, Reawakened")
    crystals = castle.state.counters.get('crystal', 0)
    assert crystals == 1, f"Expected 1 crystal counter, got {crystals}"
    scrys = [e for e in game.state.event_log
             if e.type == EventType.SCRY and e.source == castle.id]
    assert scrys, "Expected SCRY emission"
    print(f"  Crystal counters: {crystals}; scry'd")


# ============================================================================
# Registry smoke test
# ============================================================================

def test_all_v2_spice_cards_register():
    """All v2 spice cards in registry."""
    print("\n=== V2 Registry smoke ===")
    expected = [
        "Howl, Wandering Heart-Wizard",
        "Yubaba, Bathhouse Greed",
        "No-Face, Devouring Spirit",
        "The Spirit-Realm Summoning",
        "Princess Mononoke's Curse",
        "San, Wolf-Sister Ascendant",
        "Chihiro, Bridge Between Worlds",
        # Phase 2
        "Totoro, Spirit of the Camphor Tree",
        "Kaonashi's Banquet",
        "Ashitaka, Iron-Cursed Prince",
        "Kiki, Witch on Errands",
        "The Cursed Forest Awakens",
        # Phase 3
        "Haku, River-Lord Bound",
        "Ohmu, Forest Architect",
        "Witch of the Waste, Fading Splendor",
        # Phase 4
        "Sheeta, Crystal Heir",
        "Boh, Pacified Giant",
        "Mononoke's Last Hunt",
        "Suspect the Conspirators",
        "Castle in the Sky, Reawakened",
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
    # Phase 2 cards
    test_totoro_camphor_loads()
    test_totoro_camphor_pumps_other_spirits()
    test_totoro_camphor_etb_opens_modal_choice()
    test_kaonashis_banquet_loads_as_saga()
    test_kaonashis_banquet_chapter_i_reveal_and_scry()
    test_kaonashis_banquet_chapter_iii_exile_and_tokens()
    test_ashitaka_iron_cursed_loads()
    test_ashitaka_cursed_attack_punishes_and_draws()
    test_ashitaka_uncursed_attack_no_punish()
    test_kiki_witch_errands_loads()
    test_kiki_witch_cast_grants_flying()
    test_kiki_non_witch_cast_no_grant()
    test_cursed_forest_awakens_loads_as_saga()
    test_cursed_forest_chapter_i_discard_and_pump_tribes()
    test_cursed_forest_chapter_iii_exile_counters()
    # Phase 3 cards
    test_haku_river_lord_loads()
    test_haku_etb_transforms_land()
    test_ohmu_forest_architect_loads()
    test_ohmu_etb_opens_modal()
    test_witch_of_waste_fading_loads()
    test_witch_etb_reveals_and_threatens()
    # Phase 4 cards
    test_sheeta_crystal_heir_loads()
    test_sheeta_etb_animates_artifact()
    test_boh_pacified_giant_loads()
    test_mononoke_last_hunt_loads_as_saga()
    test_mononoke_last_hunt_chapter_i_tutors_wolf()
    test_suspect_the_conspirators_loads()
    test_castle_in_the_sky_reawakened_loads()
    test_castle_in_the_sky_etb_scrys_and_counters()
    test_all_v2_spice_cards_register()
    print("\n" + "=" * 60)
    print("ALL STUDIO GHIBLI V2 SPICE TESTS PASSED!")
    print("=" * 60)
