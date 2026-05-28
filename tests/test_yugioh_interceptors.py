"""
Yu-Gi-Oh! Interceptor / Effect Verification

Per-card verification: does the card actually emit events when its trigger
fires? Catches "interceptor wired but effect_fn returns []" failure mode.

This test suite was generated/updated as part of the YGO_DRAW / YGO_SEARCH_DECK
effect family work. It exercises the new draw/search helpers in
src/engine/yugioh_helpers.py.

Run directly: python tests/test_yugioh_interceptors.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.game import Game
from src.engine.types import (Event, EventType, ZoneType, CardType,
                              GameObject)
from src.engine.yugioh_helpers import (
    draw_cards, search_deck, search_deck_by_subtype,
    search_deck_by_name, add_from_gy_to_hand,
)


def make_test_game():
    g = Game(mode="yugioh")
    p1 = g.add_player("P1")
    p2 = g.add_player("P2")
    return g, p1, p2


def make_card_in_zone(game, card_def, owner_id, zone):
    chars_cls = card_def.characteristics.__class__
    chars = chars_cls(
        types=set(card_def.characteristics.types),
        subtypes=set(card_def.characteristics.subtypes or set()),
    )
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=zone,
        characteristics=chars,
        card_def=card_def,
    )


# =========================================================================
# Helper-level tests — draw_cards / search_deck / add_from_gy_to_hand
# =========================================================================

def test_draw_cards_one():
    """draw_cards(state, p, 1) moves 1 card from library to hand and emits
    a YGO_DRAW with source='draw'."""
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    card = make_ygo_monster(
        name="Test Monster", atk=1000, def_val=1000, level=4,
        attribute="DARK", ygo_monster_type="Normal",
    )
    make_card_in_zone(g, card, p1.id, ZoneType.LIBRARY)
    pre_hand = len(g.state.zones[f"hand_{p1.id}"].objects)
    events = draw_cards(g.state, p1.id, 1)
    assert len(events) == 1, f"Expected 1 YGO_DRAW event, got {len(events)}"
    assert events[0].type == EventType.YGO_DRAW
    assert events[0].payload['source'] == 'draw'
    assert events[0].payload['player'] == p1.id
    assert len(g.state.zones[f"hand_{p1.id}"].objects) == pre_hand + 1
    return True


def test_draw_cards_two():
    """draw_cards(state, p, 2) emits 2 YGO_DRAW events."""
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    for i in range(3):
        c = make_ygo_monster(
            name=f"Test {i}", atk=1000, def_val=1000, level=4,
            attribute="DARK", ygo_monster_type="Normal",
        )
        make_card_in_zone(g, c, p1.id, ZoneType.LIBRARY)
    events = draw_cards(g.state, p1.id, 2)
    assert len(events) == 2
    assert all(e.type == EventType.YGO_DRAW for e in events)
    return True


def test_draw_cards_empty_deck():
    """draw_cards on empty deck emits nothing (doesn't crash)."""
    g, p1, p2 = make_test_game()
    events = draw_cards(g.state, p1.id, 1)
    assert events == []
    return True


def test_search_deck_by_subtype():
    """search_deck_by_subtype finds card with matching subtype and emits both
    YGO_SEARCH_DECK and YGO_DRAW (source='search')."""
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    # Library: 1 Moonfolk, 1 non-Moonfolk
    moonfolk = make_ygo_monster(
        name="Soratami Test", atk=500, def_val=500, level=2,
        attribute="WATER", ygo_monster_type="Effect",
        subtypes={"Moonfolk", "Spellcaster"},
    )
    other = make_ygo_monster(
        name="Other Monster", atk=1000, def_val=1000, level=4,
        attribute="EARTH", ygo_monster_type="Normal",
        subtypes={"Warrior"},
    )
    make_card_in_zone(g, other, p1.id, ZoneType.LIBRARY)
    make_card_in_zone(g, moonfolk, p1.id, ZoneType.LIBRARY)
    events = search_deck_by_subtype(g.state, p1.id, "Moonfolk")
    assert len(events) == 2, f"Expected 2 events, got {len(events)}: {[(e.type.name, e.payload) for e in events]}"
    assert events[0].type == EventType.YGO_SEARCH_DECK
    assert events[1].type == EventType.YGO_DRAW
    assert events[1].payload['source'] == 'search'
    # Verify Moonfolk moved to hand
    hand = g.state.zones[f"hand_{p1.id}"]
    in_hand = [g.state.objects[oid].name for oid in hand.objects]
    assert "Soratami Test" in in_hand
    return True


def test_search_deck_by_subtype_max_level():
    """search_deck_by_subtype with max_level filters out higher-level matches."""
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    big_moonfolk = make_ygo_monster(
        name="Meloku Test", atk=2200, def_val=1900, level=5,
        attribute="WATER", ygo_monster_type="Effect",
        subtypes={"Moonfolk"},
    )
    small_moonfolk = make_ygo_monster(
        name="Small Moonfolk", atk=500, def_val=500, level=2,
        attribute="WATER", ygo_monster_type="Effect",
        subtypes={"Moonfolk"},
    )
    # Put big one first so it would be matched without the level cap
    make_card_in_zone(g, big_moonfolk, p1.id, ZoneType.LIBRARY)
    make_card_in_zone(g, small_moonfolk, p1.id, ZoneType.LIBRARY)
    events = search_deck_by_subtype(g.state, p1.id, "Moonfolk", max_level=4)
    assert len(events) == 2
    # The small one should be matched, not the big one
    matched_name = events[0].payload['card_name']
    assert matched_name == "Small Moonfolk", f"Got {matched_name}"
    return True


def test_search_deck_no_match():
    """search_deck with no matches emits nothing."""
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    other = make_ygo_monster(
        name="Other", atk=1000, def_val=1000, level=4,
        attribute="EARTH", ygo_monster_type="Normal", subtypes={"Warrior"},
    )
    make_card_in_zone(g, other, p1.id, ZoneType.LIBRARY)
    events = search_deck_by_subtype(g.state, p1.id, "Moonfolk")
    assert events == []
    return True


def test_search_deck_by_name():
    """search_deck_by_name finds card with exact name."""
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    target = make_ygo_monster(
        name="Blue-Eyes Test", atk=3000, def_val=2500, level=8,
        attribute="LIGHT", ygo_monster_type="Normal",
        subtypes={"Dragon"},
    )
    other = make_ygo_monster(
        name="Other Dragon", atk=2000, def_val=2000, level=6,
        attribute="LIGHT", ygo_monster_type="Normal",
        subtypes={"Dragon"},
    )
    make_card_in_zone(g, other, p1.id, ZoneType.LIBRARY)
    make_card_in_zone(g, target, p1.id, ZoneType.LIBRARY)
    events = search_deck_by_name(g.state, p1.id, "Blue-Eyes Test")
    assert len(events) == 2
    assert events[0].payload['card_name'] == "Blue-Eyes Test"
    return True


def test_add_from_gy_to_hand():
    """add_from_gy_to_hand moves a specific card from GY to hand with
    source='recovery' YGO_DRAW event."""
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    card = make_ygo_monster(
        name="Sangan Test", atk=1000, def_val=600, level=3,
        attribute="DARK", ygo_monster_type="Effect", subtypes={"Fiend"},
    )
    obj = make_card_in_zone(g, card, p1.id, ZoneType.GRAVEYARD)
    events = add_from_gy_to_hand(g.state, p1.id, obj.id)
    assert len(events) == 1
    assert events[0].type == EventType.YGO_DRAW
    assert events[0].payload['source'] == 'recovery'
    # Card is in hand now
    assert obj.id in g.state.zones[f"hand_{p1.id}"].objects
    return True


# =========================================================================
# Card-level tests — Pot of Greed, Moonfolk searcher, Sword and Shield
# =========================================================================

def test_pot_of_greed_emits_two_draws():
    """Pot of Greed resolve emits exactly 2 YGO_DRAW events."""
    from src.cards.yugioh.ygo_optimized import POT_OF_GREED
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    # Stock library with 3 cards
    for i in range(3):
        c = make_ygo_monster(
            name=f"L{i}", atk=1000, def_val=1000, level=4,
            attribute="DARK", ygo_monster_type="Normal",
        )
        make_card_in_zone(g, c, p1.id, ZoneType.LIBRARY)
    obj = make_card_in_zone(g, POT_OF_GREED, p1.id, ZoneType.HAND)
    ev = Event(type=EventType.YGO_ACTIVATE_SPELL,
               payload={'card_id': obj.id, 'player': p1.id, 'targets': []},
               source=obj.id, controller=p1.id)
    events = POT_OF_GREED.resolve(ev, g.state)
    draws = [e for e in events if e.type == EventType.YGO_DRAW]
    assert len(draws) == 2, f"Expected 2 YGO_DRAW, got {len(draws)}: {[e.payload for e in events]}"
    return True


def test_pot_of_greed_with_empty_deck():
    """Pot of Greed on empty deck emits nothing (graceful)."""
    from src.cards.yugioh.ygo_optimized import POT_OF_GREED
    g, p1, p2 = make_test_game()
    obj = make_card_in_zone(g, POT_OF_GREED, p1.id, ZoneType.HAND)
    ev = Event(type=EventType.YGO_ACTIVATE_SPELL,
               payload={'card_id': obj.id, 'player': p1.id, 'targets': []},
               source=obj.id, controller=p1.id)
    events = POT_OF_GREED.resolve(ev, g.state)
    assert events == []
    return True


def test_moonfolk_searcher_pulls_moonfolk():
    """Soratami Savant's setup-interceptor effect, when fired with a
    YGO_NORMAL_SUMMON, pulls a Moonfolk from the deck."""
    from src.cards.yugioh.beyond.kamigawa.moonfolk import (
        SORATAMI_SAVANT, SORATAMI_CLOUDSKATER,
    )
    g, p1, p2 = make_test_game()
    # Put a Moonfolk in the deck
    moonfolk_in_deck = make_card_in_zone(g, SORATAMI_CLOUDSKATER, p1.id, ZoneType.LIBRARY)
    # Put a non-Moonfolk in the deck (won't be searched)
    from src.engine.game import make_ygo_monster
    other = make_ygo_monster(
        name="Filler", atk=1000, def_val=1000, level=4,
        attribute="EARTH", ygo_monster_type="Normal", subtypes={"Warrior"},
    )
    make_card_in_zone(g, other, p1.id, ZoneType.LIBRARY)
    # Summon the searcher to the field
    savant = make_card_in_zone(g, SORATAMI_SAVANT, p1.id, ZoneType.MONSTER_ZONE)
    interceptors = SORATAMI_SAVANT.setup_interceptors(savant, g.state)
    assert len(interceptors) >= 1
    # Fire YGO_NORMAL_SUMMON for the searcher
    summon_event = Event(
        type=EventType.YGO_NORMAL_SUMMON,
        payload={'card_id': savant.id, 'player': p1.id, 'card_name': savant.name},
    )
    fired = False
    emitted = []
    for ic in interceptors:
        if ic.filter(summon_event, g.state):
            fired = True
            result = ic.handler(summon_event, g.state)
            emitted.extend(getattr(result, 'new_events', []) or [])
    assert fired, "Soratami Savant trigger should fire on its own Normal Summon"
    # Should emit YGO_DRAW (for the search result)
    draw_events = [e for e in emitted if e.type == EventType.YGO_DRAW]
    assert len(draw_events) >= 1, f"Expected YGO_DRAW from search, got {[e.type.name for e in emitted]}"
    # Card moved to hand
    hand = g.state.zones[f"hand_{p1.id}"].objects
    assert moonfolk_in_deck.id in hand, "Moonfolk should be in hand after search"
    return True


def test_sword_and_shield_emits_chain_links():
    """Sword and Shield swaps ATK/DEF and emits one YGO_CHAIN_LINK per
    affected monster (was: returned [] despite mutating state)."""
    from src.cards.yugioh.beyond.kamigawa.staples import SWORD_AND_SHIELD
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    m = make_ygo_monster(
        name="M1", atk=1200, def_val=2000, level=4,
        attribute="EARTH", ygo_monster_type="Normal",
    )
    obj = make_card_in_zone(g, m, p1.id, ZoneType.MONSTER_ZONE)
    obj.state.face_down = False
    obj.state.ygo_position = 'face_up_atk'
    g.state.zones[f"monster_zone_{p1.id}"].objects = [obj.id, None, None, None, None]
    trap_obj = make_card_in_zone(g, SWORD_AND_SHIELD, p1.id, ZoneType.SPELL_TRAP_ZONE)
    ev = Event(type=EventType.YGO_ACTIVATE_TRAP,
               payload={'card_id': trap_obj.id, 'player': p1.id, 'targets': []},
               source=trap_obj.id, controller=p1.id)
    events = SWORD_AND_SHIELD.resolve(ev, g.state)
    chain_events = [e for e in events if e.type == EventType.YGO_CHAIN_LINK]
    assert len(chain_events) >= 1, f"Sword and Shield should emit YGO_CHAIN_LINK, got: {events}"
    return True


def test_solemn_judgment_emits_lp_and_chain():
    """Solemn Judgment costs LP and emits YGO_LP_CHANGE + YGO_CHAIN_LINK."""
    from src.cards.yugioh.ygo_starter import SOLEMN_JUDGMENT
    g, p1, p2 = make_test_game()
    p1_player = g.state.players[p1.id]
    starting_lp = p1_player.lp
    obj = make_card_in_zone(g, SOLEMN_JUDGMENT, p1.id, ZoneType.SPELL_TRAP_ZONE)
    ev = Event(type=EventType.YGO_ACTIVATE_TRAP,
               payload={'card_id': obj.id, 'player': p1.id, 'targets': []},
               source=obj.id, controller=p1.id)
    events = SOLEMN_JUDGMENT.resolve(ev, g.state)
    types = [e.type for e in events]
    assert EventType.YGO_LP_CHANGE in types
    assert EventType.YGO_CHAIN_LINK in types
    assert p1_player.lp < starting_lp
    return True


def test_reciprocate_emits_chain_link():
    """Reciprocate buffs Samurai and emits YGO_CHAIN_LINK (was: silent)."""
    from src.cards.yugioh.beyond.kamigawa.samurai import RECIPROCATE
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    sam = make_ygo_monster(
        name="Samurai Test", atk=1500, def_val=1200, level=4,
        attribute="EARTH", ygo_monster_type="Effect", subtypes={"Warrior", "Samurai"},
    )
    sobj = make_card_in_zone(g, sam, p1.id, ZoneType.MONSTER_ZONE)
    g.state.zones[f"monster_zone_{p1.id}"].objects = [sobj.id, None, None, None, None]
    spell_obj = make_card_in_zone(g, RECIPROCATE, p1.id, ZoneType.HAND)
    ev = Event(type=EventType.YGO_ACTIVATE_SPELL,
               payload={'card_id': spell_obj.id, 'player': p1.id,
                        'targets': [sobj.id]},
               source=spell_obj.id, controller=p1.id)
    events = RECIPROCATE.resolve(ev, g.state)
    chain = [e for e in events if e.type == EventType.YGO_CHAIN_LINK]
    assert len(chain) >= 1, f"Reciprocate should emit chain link: {events}"
    assert sobj.state.atk_bonus_eot >= 1000
    return True


def test_bushido_honor_emits_chain_link():
    """Bushido Honor with auto-target buffs and emits YGO_CHAIN_LINK."""
    from src.cards.yugioh.beyond.kamigawa.samurai import BUSHIDO_HONOR
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    sam = make_ygo_monster(
        name="Samurai", atk=1500, def_val=1200, level=4,
        attribute="EARTH", ygo_monster_type="Effect", subtypes={"Warrior", "Samurai"},
    )
    sobj = make_card_in_zone(g, sam, p1.id, ZoneType.MONSTER_ZONE)
    g.state.zones[f"monster_zone_{p1.id}"].objects = [sobj.id, None, None, None, None]
    trap_obj = make_card_in_zone(g, BUSHIDO_HONOR, p1.id, ZoneType.SPELL_TRAP_ZONE)
    ev = Event(type=EventType.YGO_ACTIVATE_TRAP,
               payload={'card_id': trap_obj.id, 'player': p1.id, 'targets': []},
               source=trap_obj.id, controller=p1.id)
    events = BUSHIDO_HONOR.resolve(ev, g.state)
    chain = [e for e in events if e.type == EventType.YGO_CHAIN_LINK]
    assert len(chain) >= 1
    return True


def test_flute_of_summoning_dragon_with_lord_of_d():
    """Flute of Summoning Dragon with Lord of D. on field SS up to 2 Dragons."""
    from src.cards.yugioh.ygo_classic import FLUTE_OF_SUMMONING_DRAGON, LORD_OF_D, BLUE_EYES_WHITE_DRAGON
    g, p1, p2 = make_test_game()
    lord = make_card_in_zone(g, LORD_OF_D, p1.id, ZoneType.MONSTER_ZONE)
    g.state.zones[f"monster_zone_{p1.id}"].objects = [lord.id, None, None, None, None]
    # 2 Dragons in hand
    d1 = make_card_in_zone(g, BLUE_EYES_WHITE_DRAGON, p1.id, ZoneType.HAND)
    d2 = make_card_in_zone(g, BLUE_EYES_WHITE_DRAGON, p1.id, ZoneType.HAND)
    flute = make_card_in_zone(g, FLUTE_OF_SUMMONING_DRAGON, p1.id, ZoneType.HAND)
    ev = Event(type=EventType.YGO_ACTIVATE_SPELL,
               payload={'card_id': flute.id, 'player': p1.id, 'targets': []},
               source=flute.id, controller=p1.id)
    events = FLUTE_OF_SUMMONING_DRAGON.resolve(ev, g.state)
    summons = [e for e in events if e.type == EventType.YGO_SPECIAL_SUMMON]
    assert len(summons) == 2, f"Expected 2 SS, got {len(summons)}"
    return True


def test_flute_of_summoning_dragon_no_lord():
    """Flute without Lord of D. on field does nothing."""
    from src.cards.yugioh.ygo_classic import FLUTE_OF_SUMMONING_DRAGON, BLUE_EYES_WHITE_DRAGON
    g, p1, p2 = make_test_game()
    # 1 Dragon in hand, no Lord of D.
    d1 = make_card_in_zone(g, BLUE_EYES_WHITE_DRAGON, p1.id, ZoneType.HAND)
    flute = make_card_in_zone(g, FLUTE_OF_SUMMONING_DRAGON, p1.id, ZoneType.HAND)
    ev = Event(type=EventType.YGO_ACTIVATE_SPELL,
               payload={'card_id': flute.id, 'player': p1.id, 'targets': []},
               source=flute.id, controller=p1.id)
    events = FLUTE_OF_SUMMONING_DRAGON.resolve(ev, g.state)
    assert events == []
    return True


def test_negate_attack_emits_chain_link():
    """Negate Attack returns a chain link event (was: silent)."""
    from src.cards.yugioh.ygo_classic import NEGATE_ATTACK
    g, p1, p2 = make_test_game()
    trap = make_card_in_zone(g, NEGATE_ATTACK, p1.id, ZoneType.SPELL_TRAP_ZONE)
    ev = Event(type=EventType.YGO_ACTIVATE_TRAP,
               payload={'card_id': trap.id, 'player': p1.id, 'targets': []},
               source=trap.id, controller=p1.id)
    events = NEGATE_ATTACK.resolve(ev, g.state)
    assert any(e.type == EventType.YGO_CHAIN_LINK for e in events)
    return True


def test_cogwork_ambush_emits_chain_link():
    """Cogwork Ambush buffs Modified Machine and emits chain link.

    is_modified() requires an Equip Spell attached, so we attach a dummy equip.
    """
    from src.cards.yugioh.beyond.kamigawa.modified import COGWORK_AMBUSH
    from src.engine.game import make_ygo_monster, make_ygo_spell
    g, p1, p2 = make_test_game()
    mech = make_ygo_monster(
        name="Test Mech", atk=1500, def_val=1200, level=4,
        attribute="EARTH", ygo_monster_type="Effect",
        subtypes={"Machine"},
    )
    equip = make_ygo_spell(
        name="Dummy Equip", ygo_spell_type="Equip", text="test",
    )
    mobj = make_card_in_zone(g, mech, p1.id, ZoneType.MONSTER_ZONE)
    g.state.zones[f"monster_zone_{p1.id}"].objects = [mobj.id, None, None, None, None]
    eq_obj = make_card_in_zone(g, equip, p1.id, ZoneType.SPELL_TRAP_ZONE)
    eq_obj.state.equipped_to = mobj.id
    trap = make_card_in_zone(g, COGWORK_AMBUSH, p1.id, ZoneType.SPELL_TRAP_ZONE)
    ev = Event(type=EventType.YGO_ACTIVATE_TRAP,
               payload={'card_id': trap.id, 'player': p1.id,
                        'targets': [mobj.id]},
               source=trap.id, controller=p1.id)
    events = COGWORK_AMBUSH.resolve(ev, g.state)
    chain = [e for e in events if e.type == EventType.YGO_CHAIN_LINK]
    assert len(chain) >= 1, f"Expected chain link: {events}"
    return True


def test_cloak_and_dagger_emits_position_change():
    """Cloak and Dagger changes Ninja to face-down DEF and emits position change."""
    from src.cards.yugioh.beyond.kamigawa.ninja import CLOAK_AND_DAGGER
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    ninja = make_ygo_monster(
        name="Test Ninja", atk=1500, def_val=1200, level=4,
        attribute="DARK", ygo_monster_type="Effect",
        subtypes={"Warrior", "Ninja"},
    )
    nobj = make_card_in_zone(g, ninja, p1.id, ZoneType.MONSTER_ZONE)
    nobj.state.face_down = False
    g.state.zones[f"monster_zone_{p1.id}"].objects = [nobj.id, None, None, None, None]
    trap = make_card_in_zone(g, CLOAK_AND_DAGGER, p1.id, ZoneType.SPELL_TRAP_ZONE)
    ev = Event(type=EventType.YGO_ACTIVATE_TRAP,
               payload={'card_id': trap.id, 'player': p1.id, 'targets': []},
               source=trap.id, controller=p1.id)
    events = CLOAK_AND_DAGGER.resolve(ev, g.state)
    assert any(e.type == EventType.YGO_POSITION_CHANGE for e in events)
    assert nobj.state.face_down is True
    return True


def test_awakening_hour_emits_chain_link_per_spirit():
    """Awakening Hour grants protection to each Spirit and emits 1 chain link per."""
    from src.cards.yugioh.beyond.kamigawa.spirit_dragons import AWAKENING_HOUR
    from src.engine.game import make_ygo_monster
    g, p1, p2 = make_test_game()
    spirit = make_ygo_monster(
        name="Test Spirit", atk=1500, def_val=1200, level=4,
        attribute="LIGHT", ygo_monster_type="Effect",
        subtypes={"Dragon", "Spirit"},
    )
    sobj = make_card_in_zone(g, spirit, p1.id, ZoneType.MONSTER_ZONE)
    g.state.zones[f"monster_zone_{p1.id}"].objects = [sobj.id, None, None, None, None]
    spell = make_card_in_zone(g, AWAKENING_HOUR, p1.id, ZoneType.HAND)
    ev = Event(type=EventType.YGO_ACTIVATE_SPELL,
               payload={'card_id': spell.id, 'player': p1.id, 'targets': []},
               source=spell.id, controller=p1.id)
    events = AWAKENING_HOUR.resolve(ev, g.state)
    chain = [e for e in events if e.type == EventType.YGO_CHAIN_LINK]
    assert len(chain) >= 1
    assert sobj.state.battle_indestructible_eot is True
    return True


# =========================================================================
# Test runner
# =========================================================================

def main():
    tests = [
        # Helper tests
        test_draw_cards_one,
        test_draw_cards_two,
        test_draw_cards_empty_deck,
        test_search_deck_by_subtype,
        test_search_deck_by_subtype_max_level,
        test_search_deck_no_match,
        test_search_deck_by_name,
        test_add_from_gy_to_hand,
        # Card-level tests
        test_pot_of_greed_emits_two_draws,
        test_pot_of_greed_with_empty_deck,
        test_moonfolk_searcher_pulls_moonfolk,
        test_sword_and_shield_emits_chain_links,
        test_solemn_judgment_emits_lp_and_chain,
        test_reciprocate_emits_chain_link,
        test_bushido_honor_emits_chain_link,
        test_flute_of_summoning_dragon_with_lord_of_d,
        test_flute_of_summoning_dragon_no_lord,
        test_negate_attack_emits_chain_link,
        test_cogwork_ambush_emits_chain_link,
        test_cloak_and_dagger_emits_position_change,
        test_awakening_hour_emits_chain_link_per_spirit,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS: {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {t.__name__} — {e}")
            failed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ERROR: {t.__name__} — {type(e).__name__}: {e}")
            failed += 1
    total = passed + failed
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {total}")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
