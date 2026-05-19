"""
Jujutsu Kaisen Spice Pass Tests (Phase A1)

Validates the format-defining cards added to `src/cards/custom/jujutsu_kaisen.py`
in the 2026-05-18 spice pass. Mirrors `tests/test_zelda_spice.py` shape and
uses the worktree-portable sys.path per spice-pass.md gotcha #18.

Cards covered:
- Sukuna, Heian Reincarnate (NEW — Curse-tribal mythic build-around)
- Megumi, Master of Ten Shadows (NEW — Shikigami tutor on a body)
- Sukuna's Awakening (NEW — 3-chapter saga)
- Cursed Object Collection (NEW — graveyard-Curse scaling equipment)
- Unlimited Void (REWIRE — Domain Expansion asymmetric prison)
- Nue, Thunder Shikigami (REWIRE — Shikigami scaling ETB zap)
- Malevolent Shrine Keeper (REWIRE — Curse lord + drain)
- Sukuna's Finger (REWIRE — assembly piece — gather 4, tutor King)
"""

import os
import sys
# Compute repo root from this file's location so the test runs from any
# checkout (main or a `.claude/worktrees/agent-*/` worktree). Per
# spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.jujutsu_kaisen import JUJUTSU_KAISEN_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the Zelda spice test harness.

    `create_object` runs `setup_interceptors` for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with `card_def=None`, then ZONE_CHANGE
    to battlefield, runs setup exactly once via the pipeline."""
    card_def = JUJUTSU_KAISEN_CARDS[card_name]
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
    """Spawn a card directly into a player's graveyard for synergy setup."""
    card_def = JUJUTSU_KAISEN_CARDS[card_name]
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
# Sukuna, Heian Reincarnate
# ============================================================================

def test_sukuna_heian_loads():
    print("\n=== Sukuna, Heian Reincarnate: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sukuna = _put_on_battlefield(game, p1, "Sukuna, Heian Reincarnate")
    assert sukuna.zone == ZoneType.BATTLEFIELD
    # Expect: ETB trigger + Curse-death trigger + keyword grant (conditional).
    assert len(sukuna.interceptor_ids) >= 3, (
        f"Expected at least 3 interceptors; got {len(sukuna.interceptor_ids)}"
    )


def test_sukuna_heian_etb_each_opp_sacs():
    """ETB emits SACRIFICE_REQUIRED to each opponent."""
    print("\n=== Sukuna Heian: ETB each opp sacrifices ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Sukuna, Heian Reincarnate")
    new = game.state.event_log[before:]
    sac_events = [
        e for e in new
        if e.type == EventType.SACRIFICE_REQUIRED
        and e.payload.get('card_type') == 'creature'
    ]
    sac_players = {e.payload.get('player') for e in sac_events}
    assert p2.id in sac_players, "Expected opponent SACRIFICE_REQUIRED"
    assert p1.id not in sac_players, "Sukuna's controller should not sac"


def test_sukuna_heian_curse_death_grows_him():
    """When another Curse you control dies, +1/+1 counter on Sukuna."""
    print("\n=== Sukuna Heian: curse death grows ===")
    game = Game()
    p1 = game.add_player("Alice")
    sukuna = _put_on_battlefield(game, p1, "Sukuna, Heian Reincarnate")
    # Put another Curse onto the battlefield, then send it to graveyard.
    curse_def = JUJUTSU_KAISEN_CARDS["Finger Bearer"]  # known Curse creature
    curse_obj = game.create_object(
        name="Finger Bearer", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=curse_def.characteristics, card_def=None,
    )
    curse_obj.card_def = curse_def
    bf = game.state.zones.get('battlefield')
    if bf and curse_obj.id not in bf.objects:
        bf.objects.append(curse_obj.id)

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': curse_obj.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == sukuna.id
        and e.payload.get('counter_type') == '+1/+1'
    ]
    assert counters, (
        f"Expected +1/+1 counter on Sukuna after Curse death; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_sukuna_heian_self_death_does_not_self_grow():
    """Edge: Sukuna himself dying does NOT add a counter (filter excludes self)."""
    print("\n=== Sukuna Heian: self-death does not feed ===")
    game = Game()
    p1 = game.add_player("Alice")
    sukuna = _put_on_battlefield(game, p1, "Sukuna, Heian Reincarnate")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': sukuna.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    counters = [
        e for e in new
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == sukuna.id
    ]
    assert not counters, "Sukuna should not feed on own death"


def test_sukuna_heian_trample_menace_only_with_four_curses():
    """4+ Curses gates trample+menace via keyword_grant."""
    print("\n=== Sukuna Heian: trample+menace gate ===")
    game = Game()
    p1 = game.add_player("Alice")
    sukuna = _put_on_battlefield(game, p1, "Sukuna, Heian Reincarnate")
    # Without other Curses (Sukuna himself counts as 1 Curse via subtype).
    assert not has_ability(sukuna, 'trample', game.state)
    # Add 3 more Curses (Sukuna himself counts, so 4 total).
    for name in ["Finger Bearer", "Cursed Womb", "Vengeful Cursed Spirit"]:
        _put_on_battlefield(game, p1, name)
    assert has_ability(sukuna, 'trample', game.state), (
        "Expected trample after 4 Curses"
    )
    assert has_ability(sukuna, 'menace', game.state), (
        "Expected menace after 4 Curses"
    )


# ============================================================================
# Megumi, Master of Ten Shadows
# ============================================================================

def test_megumi_ten_shadows_loads():
    print("\n=== Megumi, Ten Shadows Master: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    megumi = _put_on_battlefield(game, p1, "Megumi, Master of Ten Shadows")
    assert megumi.zone == ZoneType.BATTLEFIELD
    # ETB tutor + static anthem (P+T = 2 interceptors) + attack draw = 4+.
    assert len(megumi.interceptor_ids) >= 3, (
        f"Expected at least 3 interceptors; got {len(megumi.interceptor_ids)}"
    )


def test_megumi_ten_shadows_etb_tutors_shikigami():
    """ETB emits SEARCH_LIBRARY for a Shikigami creature card MV<=3."""
    print("\n=== Megumi: ETB Shikigami tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Megumi, Master of Ten Shadows")
    new = game.state.event_log[before:]
    searches = [
        e for e in new
        if e.type == EventType.SEARCH_LIBRARY
        and e.payload.get('subtype') == 'Shikigami'
        and e.payload.get('destination') == 'battlefield'
        and e.payload.get('mana_value_max') == 3
    ]
    assert searches, (
        f"Expected ETB SEARCH_LIBRARY for Shikigami MV<=3; "
        f"recent={_emitted_types(game)[-10:]}"
    )


def test_megumi_ten_shadows_anthem_buffs_shikigami():
    """Other Shikigami you control get +1/+1."""
    print("\n=== Megumi: anthem buffs Shikigami ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Add a Shikigami first to measure baseline.
    dog = _put_on_battlefield(game, p1, "Divine Dog: Black")
    base_p = get_power(dog, game.state)
    base_t = get_toughness(dog, game.state)
    _put_on_battlefield(game, p1, "Megumi, Master of Ten Shadows")
    new_p = get_power(dog, game.state)
    new_t = get_toughness(dog, game.state)
    assert new_p == base_p + 1, f"Power: {base_p}->{new_p}"
    assert new_t == base_t + 1, f"Toughness: {base_t}->{new_t}"


def test_megumi_ten_shadows_anthem_excludes_non_shikigami():
    """Megumi's anthem does NOT buff non-Shikigami creatures."""
    print("\n=== Megumi: anthem excludes non-Shikigami ===")
    game = Game()
    p1 = game.add_player("Alice")
    # A non-Shikigami creature (Jujutsu Trainee is Human Sorcerer).
    trainee = _put_on_battlefield(game, p1, "Jujutsu Trainee")
    base_p = get_power(trainee, game.state)
    _put_on_battlefield(game, p1, "Megumi, Master of Ten Shadows")
    new_p = get_power(trainee, game.state)
    assert new_p == base_p, f"Non-Shikigami unexpectedly buffed: {base_p}->{new_p}"


def test_megumi_ten_shadows_shikigami_attack_draws():
    """Your Shikigami attacking emits DRAW."""
    print("\n=== Megumi: Shikigami attack -> draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Megumi, Master of Ten Shadows")
    dog = _put_on_battlefield(game, p1, "Divine Dog: Black")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': dog.id, 'attacker': dog.id, 'controller': p1.id},
        source=dog.id,
    ))
    new = game.state.event_log[before:]
    draws = [
        e for e in new
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    assert draws, (
        f"Expected DRAW on Shikigami attack; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


# ============================================================================
# Sukuna's Awakening (saga)
# ============================================================================

def test_sukuna_awakening_loads_as_saga():
    print("\n=== Sukuna's Awakening: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Sukuna's Awakening")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert saga.interceptor_ids, "Saga should register chapter interceptors"


def test_sukuna_awakening_chapter_i_drains_opps():
    print("\n=== Sukuna's Awakening: chapter I ===")
    from src.cards.custom.jujutsu_kaisen import _sukuna_awakening_chapter_i
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    saga = _put_on_battlefield(game, p1, "Sukuna's Awakening")
    events = _sukuna_awakening_chapter_i(saga, game.state)
    drains = [
        e for e in events
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -2
    ]
    assert drains, f"Expected -2 life to opp; got {[e.type.name for e in events]}"


def test_sukuna_awakening_chapter_ii_creates_two_curses():
    print("\n=== Sukuna's Awakening: chapter II ===")
    from src.cards.custom.jujutsu_kaisen import _sukuna_awakening_chapter_ii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Sukuna's Awakening")
    events = _sukuna_awakening_chapter_ii(saga, game.state)
    tokens = [
        e for e in events
        if e.type == EventType.CREATE_TOKEN
        and e.payload.get('token', {}).get('subtypes', set()) & {'Curse'}
    ]
    assert len(tokens) == 2, f"Expected 2 Curse tokens; got {len(tokens)}"


def test_sukuna_awakening_chapter_iii_tutors_curse():
    print("\n=== Sukuna's Awakening: chapter III ===")
    from src.cards.custom.jujutsu_kaisen import _sukuna_awakening_chapter_iii
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Sukuna's Awakening")
    events = _sukuna_awakening_chapter_iii(saga, game.state)
    searches = [
        e for e in events
        if e.type == EventType.SEARCH_LIBRARY
        and e.payload.get('subtype') == 'Curse'
        and e.payload.get('destination') == 'battlefield'
    ]
    assert searches, f"Expected SEARCH_LIBRARY for Curse to battlefield"


# ============================================================================
# Cursed Object Collection (equipment)
# ============================================================================

def test_cursed_object_collection_loads():
    print("\n=== Cursed Object Collection: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    coc = _put_on_battlefield(game, p1, "Cursed Object Collection")
    assert coc.zone == ZoneType.BATTLEFIELD
    # Expect dynamic PT (2 interceptors: power + toughness queries) + keyword.
    assert len(coc.interceptor_ids) >= 2, (
        f"Expected >= 2 interceptors; got {len(coc.interceptor_ids)}"
    )
    activated = getattr(coc.state, 'activated_abilities', None)
    assert activated, "Expected equip activated ability"


def test_cursed_object_collection_scales_with_grave_curses():
    """When attached, equipped creature gets +X/+X where X = Curse cards in gy."""
    print("\n=== Cursed Object Collection: +X/+X from gy ===")
    game = Game()
    p1 = game.add_player("Alice")
    coc = _put_on_battlefield(game, p1, "Cursed Object Collection")
    trainee = _put_on_battlefield(game, p1, "Jujutsu Trainee")
    base_p = get_power(trainee, game.state)
    base_t = get_toughness(trainee, game.state)
    # Attach.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': coc.id, 'target_id': trainee.id},
        source=coc.id,
    ))
    # With empty graveyard, X = 0; equipped creature unchanged.
    p_after_empty = get_power(trainee, game.state)
    t_after_empty = get_toughness(trainee, game.state)
    assert p_after_empty == base_p, f"Empty-gy power: {base_p}->{p_after_empty}"
    assert t_after_empty == base_t, f"Empty-gy toughness: {base_t}->{t_after_empty}"

    # Now plant 2 Curse creature cards in p1's graveyard.
    _put_in_graveyard(game, p1, "Finger Bearer")  # is Curse creature
    _put_in_graveyard(game, p1, "Cursed Womb")    # is Curse creature

    p_after_two = get_power(trainee, game.state)
    t_after_two = get_toughness(trainee, game.state)
    assert p_after_two == base_p + 2, (
        f"Expected +2 from 2 gy Curses: {base_p}->{p_after_two}"
    )
    assert t_after_two == base_t + 2, (
        f"Expected +2 toughness: {base_t}->{t_after_two}"
    )


def test_cursed_object_collection_menace_on_attach():
    """Equipped creature gains menace."""
    print("\n=== Cursed Object Collection: menace ===")
    game = Game()
    p1 = game.add_player("Alice")
    coc = _put_on_battlefield(game, p1, "Cursed Object Collection")
    trainee = _put_on_battlefield(game, p1, "Jujutsu Trainee")
    assert not has_ability(trainee, 'menace', game.state)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': coc.id, 'target_id': trainee.id},
        source=coc.id,
    ))
    assert has_ability(trainee, 'menace', game.state), (
        "Expected menace after attach"
    )


# ============================================================================
# Unlimited Void (rewire)
# ============================================================================

def test_unlimited_void_loads():
    print("\n=== Unlimited Void: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    void = _put_on_battlefield(game, p1, "Unlimited Void")
    assert void.zone == ZoneType.BATTLEFIELD
    # Expect PT interceptors (2) + upkeep trigger (1) = 3+.
    assert len(void.interceptor_ids) >= 2


def test_unlimited_void_static_minus_minus_opp_creatures():
    """Creatures opponents control get -1/-1."""
    print("\n=== Unlimited Void: opp -1/-1 ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    enemy = _put_on_battlefield(game, p2, "Jujutsu Trainee")
    base_p = get_power(enemy, game.state)
    base_t = get_toughness(enemy, game.state)
    _put_on_battlefield(game, p1, "Unlimited Void")
    new_p = get_power(enemy, game.state)
    new_t = get_toughness(enemy, game.state)
    assert new_p == base_p - 1, f"Opp power: {base_p}->{new_p}"
    assert new_t == base_t - 1, f"Opp tough: {base_t}->{new_t}"


def test_unlimited_void_static_does_not_hit_own_creatures():
    """Your own creatures are NOT debuffed."""
    print("\n=== Unlimited Void: own creature unaffected ===")
    game = Game()
    p1 = game.add_player("Alice")
    friendly = _put_on_battlefield(game, p1, "Jujutsu Trainee")
    base_p = get_power(friendly, game.state)
    _put_on_battlefield(game, p1, "Unlimited Void")
    new_p = get_power(friendly, game.state)
    assert new_p == base_p, f"Own creature debuffed: {base_p}->{new_p}"


def test_unlimited_void_upkeep_discards_opps():
    """Your upkeep emits DISCARD to each opp."""
    print("\n=== Unlimited Void: upkeep discard ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Unlimited Void")
    # Per gotcha #8: upkeep filter on state.active_player.
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    discards = [
        e for e in new
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
    ]
    assert discards, (
        f"Expected DISCARD on opp during own upkeep; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


# ============================================================================
# Nue, Thunder Shikigami (rewire)
# ============================================================================

def test_nue_thunder_loads_with_flying():
    print("\n=== Nue, Thunder Shikigami: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    nue = _put_on_battlefield(game, p1, "Nue, Thunder Shikigami")
    assert nue.zone == ZoneType.BATTLEFIELD
    assert has_ability(nue, 'flying', game.state), (
        "Nue should have flying after self-keyword grant"
    )


def test_nue_thunder_etb_zaps_small_opp_creatures():
    """ETB deals damage to opp creatures with T<=2."""
    print("\n=== Nue: ETB zaps small opp creatures ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Opp creatures of various T.
    small = _put_on_battlefield(game, p2, "Jujutsu Trainee")  # 2/1
    big = _put_on_battlefield(game, p2, "Jujutsu Veteran")    # check
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Nue, Thunder Shikigami")
    new = game.state.event_log[before:]
    dmgs_to_small = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == small.id
    ]
    assert dmgs_to_small, (
        f"Expected DAMAGE to opp small creature; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )
    # Big should NOT be in the damage list (T>2).
    big_t = get_toughness(big, game.state)
    if big_t > 2:
        dmgs_to_big = [
            e for e in new
            if e.type == EventType.DAMAGE
            and e.payload.get('target') == big.id
        ]
        assert not dmgs_to_big, (
            f"Big creature (T={big_t}) should not be zapped"
        )


def test_nue_thunder_etb_no_zap_when_no_small_opp():
    """Edge: opp has no small creatures -> no DAMAGE events emitted."""
    print("\n=== Nue: empty board -> no zap ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    nue = _put_on_battlefield(game, p1, "Nue, Thunder Shikigami")
    new = game.state.event_log[before:]
    # Filter DAMAGE events sourced from Nue.
    dmgs = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('source') == nue.id
    ]
    assert not dmgs, f"Expected no DAMAGE from Nue with no opp creatures; got {len(dmgs)}"


# ============================================================================
# Malevolent Shrine Keeper (rewire)
# ============================================================================

def test_malevolent_shrine_keeper_loads():
    print("\n=== Malevolent Shrine Keeper: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    keeper = _put_on_battlefield(game, p1, "Malevolent Shrine Keeper")
    assert keeper.zone == ZoneType.BATTLEFIELD
    assert keeper.interceptor_ids


def test_malevolent_shrine_keeper_buffs_other_curses():
    """Other Curses you control get +1/+1."""
    print("\n=== Malevolent Shrine Keeper: anthem ===")
    game = Game()
    p1 = game.add_player("Alice")
    finger_bearer = _put_on_battlefield(game, p1, "Finger Bearer")  # Curse
    base_p = get_power(finger_bearer, game.state)
    base_t = get_toughness(finger_bearer, game.state)
    _put_on_battlefield(game, p1, "Malevolent Shrine Keeper")
    new_p = get_power(finger_bearer, game.state)
    new_t = get_toughness(finger_bearer, game.state)
    assert new_p == base_p + 1, f"Curse anthem power: {base_p}->{new_p}"
    assert new_t == base_t + 1, f"Curse anthem toughness: {base_t}->{new_t}"


def test_malevolent_shrine_keeper_drain_on_curse_death():
    """Whenever a Curse you control dies, each opp loses 1 life."""
    print("\n=== Malevolent Shrine Keeper: drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Malevolent Shrine Keeper")
    # Add a Curse creature.
    curse_def = JUJUTSU_KAISEN_CARDS["Finger Bearer"]
    curse_obj = game.create_object(
        name="Finger Bearer", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=curse_def.characteristics, card_def=None,
    )
    curse_obj.card_def = curse_def
    bf = game.state.zones.get('battlefield')
    if bf and curse_obj.id not in bf.objects:
        bf.objects.append(curse_obj.id)

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': curse_obj.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert drains, (
        f"Expected -1 life to opp on Curse death; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


# ============================================================================
# Sukuna's Finger (rewire)
# ============================================================================

def test_sukuna_finger_loads_indestructible():
    print("\n=== Sukuna's Finger: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    finger = _put_on_battlefield(game, p1, "Sukuna's Finger")
    assert finger.zone == ZoneType.BATTLEFIELD
    assert has_ability(finger, 'indestructible', game.state)


def test_sukuna_finger_end_step_no_tutor_with_few_fingers():
    """End step with <4 Fingers should NOT emit SEARCH_LIBRARY."""
    print("\n=== Sukuna's Finger: <4 -> no tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    _put_on_battlefield(game, p1, "Sukuna's Finger")
    # Per gotcha #8 — end-step trigger filters on state.active_player.
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    tutors = [
        e for e in new
        if e.type == EventType.SEARCH_LIBRARY
        and e.payload.get('card_name_any')
    ]
    assert not tutors, "Should not tutor with only 1 Finger"


def test_sukuna_finger_end_step_tutors_with_four_fingers():
    """End step with 4+ Fingers emits SEARCH_LIBRARY for Sukuna by name."""
    print("\n=== Sukuna's Finger: 4 -> tutor ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Spawn 4 Fingers. Each registers an end-step interceptor; only the
    # first one should successfully tutor (others see >=4 too).
    fingers = []
    for _ in range(4):
        f = _put_on_battlefield(game, p1, "Sukuna's Finger")
        fingers.append(f)
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    tutors = [
        e for e in new
        if e.type == EventType.SEARCH_LIBRARY
        and 'card_name_any' in e.payload
    ]
    assert tutors, (
        f"Expected SEARCH_LIBRARY by name; recent={[e.type.name for e in new[-10:]]}"
    )
    # Confirm the tutor names match our two Sukuna candidates.
    names = set(tutors[0].payload.get('card_name_any', []))
    assert "Ryomen Sukuna, King of Curses" in names
    assert "Sukuna, Heian Reincarnate" in names


# ============================================================================
# Phase A2 (slice 3) — decision-axis flips (2026-05-19)
#
# Each card surfaces a DISTINCT decision-axis fingerprint JJK has never
# had. Tests verify the interceptors load and the expected pipeline
# events (TARGET_REQUIRED / pending_choice install) fire on ETB.
# ============================================================================


# ----- Domain Expansion: Malevolent Shrine (modal-ETB) -----


def test_domain_malevolent_shrine_loads():
    print("\n=== Domain Expansion: Malevolent Shrine: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    dom = _put_on_battlefield(game, p1, "Domain Expansion: Malevolent Shrine")
    assert dom.zone == ZoneType.BATTLEFIELD
    assert dom.interceptor_ids, "Expected modal-ETB interceptor"


def test_domain_malevolent_shrine_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== Domain Expansion: Malevolent Shrine: modal pending ===")
    game = Game()
    p1 = game.add_player("Alice")
    dom = _put_on_battlefield(game, p1, "Domain Expansion: Malevolent Shrine")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == dom.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"


# ----- Yuta Okkotsu, Rika Unbound (targeted-ETB + info pulse) -----


def test_yuta_okkotsu_rika_unbound_loads():
    print("\n=== Yuta Okkotsu, Rika Unbound: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    yuta = _put_on_battlefield(game, p1, "Yuta Okkotsu, Rika Unbound")
    assert yuta.zone == ZoneType.BATTLEFIELD
    # Flying-grant + targeted-ETB + info-pulse closure = 3+ interceptors.
    assert len(yuta.interceptor_ids) >= 2, (
        f"Expected at least 2 interceptors; got {len(yuta.interceptor_ids)}"
    )
    assert has_ability(yuta, 'flying', game.state), "Expected flying"


def test_yuta_okkotsu_etb_emits_target_required_and_info():
    """ETB emits TARGET_REQUIRED with opponent_creature filter + a
    TARGET_CHOSEN info event from the supplementary hook."""
    print("\n=== Yuta Okkotsu: ETB target + info pulse ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    yuta = _put_on_battlefield(game, p1, "Yuta Okkotsu, Rika Unbound")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == yuta.id
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected opponent_creature TARGET_REQUIRED; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )
    info_events = [
        e for e in new
        if e.type == EventType.TARGET_CHOSEN and e.payload.get('source') == yuta.id
    ]
    assert info_events, "Expected TARGET_CHOSEN info pulse on Yuta ETB"


# ----- Black Flash Cascade (divided damage ETB) -----


def test_black_flash_cascade_loads():
    print("\n=== Black Flash Cascade: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bfc = _put_on_battlefield(game, p1, "Black Flash Cascade")
    assert bfc.zone == ZoneType.BATTLEFIELD
    assert bfc.interceptor_ids, "Expected divided-damage ETB interceptor"


def test_black_flash_cascade_etb_emits_divided_damage_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=5 and damage effect."""
    print("\n=== Black Flash Cascade: ETB distribute damage ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    bfc = _put_on_battlefield(game, p1, "Black Flash Cascade")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == bfc.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 5, (
        f"Expected divide_amount=5; got {payload.get('divide_amount')}"
    )


# ----- Mahito, Idle Transfiguration (sacrifice choice from ETB) -----


def test_mahito_idle_transfiguration_loads():
    print("\n=== Mahito, Idle Transfiguration: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    mahito = _put_on_battlefield(game, p1, "Mahito, Idle Transfiguration")
    assert mahito.zone == ZoneType.BATTLEFIELD
    assert mahito.interceptor_ids, "Expected ETB interceptor"
    assert has_ability(mahito, 'menace', game.state), "Expected menace"


def test_mahito_etb_with_opp_creature_opens_sacrifice_choice():
    """ETB opens a sacrifice pending_choice on the opponent who controls
    a creature."""
    print("\n=== Mahito: ETB opens sacrifice choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Plant an opp creature first.
    _put_on_battlefield(game, p2, "Jujutsu Trainee")
    mahito = _put_on_battlefield(game, p1, "Mahito, Idle Transfiguration")
    pc = game.state.pending_choice
    assert pc is not None, "Expected sacrifice pending_choice"
    assert pc.source_id == mahito.id
    assert pc.choice_type == "sacrifice"
    assert pc.player == p2.id, f"Expected sacrificer=p2; got {pc.player}"


def test_mahito_etb_empty_opponent_board_no_crash():
    """ETB with no opp creatures returns cleanly, no choice installed."""
    print("\n=== Mahito: empty opp board no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    mahito = _put_on_battlefield(game, p1, "Mahito, Idle Transfiguration")
    assert mahito.zone == ZoneType.BATTLEFIELD
    # No opp creatures means no sacrifice prompt triggered for Mahito.
    pc = game.state.pending_choice
    if pc is not None:
        assert pc.source_id != mahito.id, (
            "Mahito should not install a choice with empty opp board"
        )


# ----- Hakari Kinji, Idle Death Gamble (top-N land pick) -----


def test_hakari_idle_death_gamble_loads():
    print("\n=== Hakari Kinji, Idle Death Gamble: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    hakari = _put_on_battlefield(game, p1, "Hakari Kinji, Idle Death Gamble")
    assert hakari.zone == ZoneType.BATTLEFIELD
    assert hakari.interceptor_ids, "Expected ETB interceptor"
    assert has_ability(hakari, 'haste', game.state), "Expected haste"


def test_hakari_empty_library_no_crash():
    """ETB with empty library returns [] without crashing."""
    print("\n=== Hakari: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    hakari = _put_on_battlefield(game, p1, "Hakari Kinji, Idle Death Gamble")
    assert hakari.zone == ZoneType.BATTLEFIELD


# ----- Toji Fushiguro, Heavenly Pact (targeted attack trigger) -----


def test_toji_heavenly_pact_loads():
    print("\n=== Toji Fushiguro, Heavenly Pact: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    toji = _put_on_battlefield(game, p1, "Toji Fushiguro, Heavenly Pact")
    assert toji.zone == ZoneType.BATTLEFIELD
    # First-strike grant + targeted-attack trigger = 2 interceptors.
    assert len(toji.interceptor_ids) >= 2, (
        f"Expected at least 2 interceptors; got {len(toji.interceptor_ids)}"
    )
    assert has_ability(toji, 'first strike', game.state), "Expected first strike"


def test_toji_heavenly_pact_attack_emits_target_required():
    """Attack emits TARGET_REQUIRED with opponent_creature filter + damage
    effect."""
    print("\n=== Toji: attack triggers spear-strike ===")
    game = Game()
    p1 = game.add_player("Alice")
    toji = _put_on_battlefield(game, p1, "Toji Fushiguro, Heavenly Pact")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': toji.id, 'attacker': toji.id, 'controller': p1.id},
        source=toji.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == toji.id
        and e.payload.get('effect') == 'damage'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED on attack; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('effect_params', {}).get('amount') == 2, (
        f"Expected damage amount=2; got {payload.get('effect_params')}"
    )


# ============================================================================
# Runner
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
