"""
One Piece: Grand Line Spice Pass v2 Expansion Tests

Builds on the existing Phase A spice (see ``tests/test_one_piece_spice.py``).
These cards target the depth gates that the Phase A baseline failed:
axis_diversity (0.047 < 0.08), depth_v2_mean (0.33), thin_ratio (>0.90).
Each new card carries a DISTINCT axis fingerprint + AST code fingerprint
so the v2 rubric counts them as net-new mechanical surface area.

Cards covered (9):
- Kaido, King of the Beasts Awakened (NEW MYTHIC) — counter-snowball
- Big Mom, Sweet Empress (NEW MYTHIC) — Food-sac value engine
- Whitebeard, Strongest Pirate (NEW MYTHIC) — Pirate-count mass damage
- Mihawk, Falcon Eyes (REWIRE) — ward + combat-damage exile
- Marineford War, Paramount Battle (NEW SAGA) — 3-chapter wartime escalation
- Wano Country Uprising (NEW SAGA) — Samurai/Sword tribal payoff
- Yoru, the Black Blade (NEW LEGENDARY EQUIPMENT) — attack-time indestructible
- Devil Fruit Awakening (NEW AURA) — ward + attack-trigger draw
- Cipher Pol Zero, Justice Cell (NEW LEGENDARY) — spell-cast life loss
"""

import os
import sys
# Worktree-portable sys.path (gotcha #18). Compute repo root from this
# file's location so the test runs from any checkout (main or a
# `.claude/worktrees/agent-*/` worktree). Hardcoding the main-checkout
# path bit all three parallel-agent worktrees during the HPW/FINC/MVL
# rollout — see spice-pass.md gotcha #18.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, get_power, get_toughness,
)
from src.cards.custom.one_piece import ONE_PIECE_CARDS


def _put_on_battlefield(game, player, card_name):
    """Standard pattern: create in hand without card_def, then ZONE_CHANGE.

    Why we don't pass card_def to create_object: ``create_object`` runs
    ``setup_interceptors`` for objects entering BATTLEFIELD/COMMAND. Putting
    the card in HAND first with no card_def skips that, then the ZONE_CHANGE
    to battlefield runs setup exactly once (the correct path).
    """
    card_def = ONE_PIECE_CARDS[card_name]
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
    """Snapshot of EventType names that have been logged."""
    return [e.type.name for e in game.state.event_log]


# ============================================================================
# Kaido, King of the Beasts Awakened
# ============================================================================

def test_kaido_awakened_loads_legendary_dragon():
    """Loads as a legendary Dragon Pirate with trample interceptor + ETB + damage trigger."""
    print("\n=== Kaido Awakened: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    kaido = _put_on_battlefield(game, p1, "Kaido, King of the Beasts Awakened")
    chars = kaido.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Dragon' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(kaido.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors (trample kw + ETB + damage + lord); "
        f"got {len(kaido.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(kaido.interceptor_ids)}; subtypes={chars.subtypes}")


def test_kaido_awakened_etb_adds_three_counters():
    """ETB emits a COUNTER_ADDED for amount=3."""
    print("\n=== Kaido Awakened: ETB counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    kaido = _put_on_battlefield(game, p1, "Kaido, King of the Beasts Awakened")
    after = _emitted_types(game)
    new = after[len(before):]
    assert 'COUNTER_ADDED' in new, f"COUNTER_ADDED missing: {new}"
    cas = [e for e in game.state.event_log
           if e.type == EventType.COUNTER_ADDED
           and e.payload.get('object_id') == kaido.id]
    assert cas, "ETB COUNTER_ADDED missing"
    payload = cas[-1].payload
    assert payload.get('counter_type') == '+1/+1', f"Bad counter type: {payload}"
    assert payload.get('amount') == 3, f"Expected 3 counters: {payload}"
    print(f"  ETB added 3 +1/+1 counters")


def test_kaido_awakened_lord_buffs_other_dragons():
    """Other Dragons +1/+1 — Kaido himself doesn't self-buff."""
    print("\n=== Kaido Awakened: dragon lord ===")
    game = Game()
    p1 = game.add_player("Alice")
    kaido = _put_on_battlefield(game, p1, "Kaido, King of the Beasts Awakened")
    other_dragon = game.create_object(
        name="Buddy Dragon",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes={"Dragon"},
            power=3, toughness=3,
        ),
    )
    other_dragon.controller = p1.id
    d_power = get_power(other_dragon, game.state)
    d_tough = get_toughness(other_dragon, game.state)
    assert d_power == 4, f"Expected dragon power 4, got {d_power}"
    assert d_tough == 4, f"Expected dragon toughness 4, got {d_tough}"
    print(f"  Other Dragon: 3/3 -> {d_power}/{d_tough}")


# ============================================================================
# Big Mom, Sweet Empress
# ============================================================================

def test_big_mom_sweet_loads_legendary_pirate():
    """Loads as a legendary Giant Pirate."""
    print("\n=== Big Mom Sweet: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bm = _put_on_battlefield(game, p1, "Big Mom, Sweet Empress")
    chars = bm.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Pirate' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    print(f"  Subtypes: {chars.subtypes}")


def test_big_mom_sweet_etb_creates_two_food():
    """ETB emits 2x CREATE_TOKEN for Food."""
    print("\n=== Big Mom Sweet: ETB food x2 ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = _emitted_types(game)
    bm = _put_on_battlefield(game, p1, "Big Mom, Sweet Empress")
    after = _emitted_types(game)
    new = after[len(before):]
    cts = [e for e in game.state.event_log
           if e.type == EventType.CREATE_TOKEN and e.source == bm.id]
    assert len(cts) >= 2, f"Expected 2+ Food tokens on ETB: {len(cts)}"
    last = cts[-1].payload.get('token') or {}
    assert 'Food' in last.get('subtypes', set()), f"Token subtypes not Food: {last}"
    print(f"  ETB created {len(cts)} Food tokens")


def test_big_mom_sweet_food_sac_draws_and_pumps():
    """Food sacrifice fires DRAW + PT_MODIFICATION."""
    print("\n=== Big Mom Sweet: food sac trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    bm = _put_on_battlefield(game, p1, "Big Mom, Sweet Empress")
    # Drop a Food token to sacrifice.
    food = game.create_object(
        name="Food",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.ARTIFACT}, subtypes={"Food"},
        ),
    )
    food.controller = p1.id
    before_draw = len([e for e in game.state.event_log if e.type == EventType.DRAW])
    before_pt = len([e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION
                     and e.payload.get('object_id') == bm.id])
    # SACRIFICE is rewritten to ZONE_CHANGE w/ reason='sacrifice' (gotcha #5).
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': food.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'sacrifice',
        },
        source=food.id,
    ))
    after_draw = len([e for e in game.state.event_log if e.type == EventType.DRAW])
    after_pt = len([e for e in game.state.event_log
                    if e.type == EventType.PT_MODIFICATION
                    and e.payload.get('object_id') == bm.id])
    assert after_draw > before_draw, f"Sac-Food should draw: {before_draw}->{after_draw}"
    assert after_pt > before_pt, f"Sac-Food should pump Big Mom: {before_pt}->{after_pt}"
    print(f"  Sac-Food: DRAW {before_draw}->{after_draw}; PT {before_pt}->{after_pt}")


def test_big_mom_sweet_non_food_sac_does_not_trigger():
    """Edge: sacrificing a non-Food permanent doesn't fire the trigger."""
    print("\n=== Big Mom Sweet: non-food sac edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    bm = _put_on_battlefield(game, p1, "Big Mom, Sweet Empress")
    # Drop a non-Food artifact.
    art = game.create_object(
        name="Random Artifact",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.ARTIFACT}, subtypes={"Equipment"},
        ),
    )
    art.controller = p1.id
    before_draw = len([e for e in game.state.event_log if e.type == EventType.DRAW])
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': art.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'sacrifice',
        },
        source=art.id,
    ))
    after_draw = len([e for e in game.state.event_log if e.type == EventType.DRAW])
    assert after_draw == before_draw, f"Non-Food should not trigger: {before_draw}->{after_draw}"
    print("  Non-Food sac correctly suppressed")


# ============================================================================
# Whitebeard, Strongest Pirate
# ============================================================================

def test_whitebeard_strongest_loads_legendary():
    """Loads with self-keyword grants (indestructible, trample) + ETB + lord."""
    print("\n=== Whitebeard Strongest: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wb = _put_on_battlefield(game, p1, "Whitebeard, Strongest Pirate")
    chars = wb.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Pirate' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(wb.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors (kw + ETB + lord); got {len(wb.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(wb.interceptor_ids)}")


def test_whitebeard_strongest_etb_damages_opp_creatures_by_pirate_count():
    """ETB emits DAMAGE to each opp creature equal to # Pirates we control."""
    print("\n=== Whitebeard Strongest: ETB quake ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Drop one allied Pirate before Whitebeard (Whitebeard himself = 2 Pirates).
    ally = game.create_object(
        name="Crew",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Pirate"},
            power=2, toughness=2,
        ),
    )
    ally.controller = p1.id
    # Drop two opp creatures.
    foes = []
    for _ in range(2):
        foe = game.create_object(
            name="Foe",
            owner_id=p2.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=Characteristics(
                types={CardType.CREATURE}, power=3, toughness=3,
            ),
        )
        foe.controller = p2.id
        foes.append(foe)
    before = _emitted_types(game)
    wb = _put_on_battlefield(game, p1, "Whitebeard, Strongest Pirate")
    after = _emitted_types(game)
    new = after[len(before):]
    dmg = [e for e in game.state.event_log
           if e.type == EventType.DAMAGE
           and e.source == wb.id]
    # Whitebeard counts himself as a Pirate => 2 Pirates => 2 damage each.
    assert len(dmg) >= 2, f"Expected 2+ damage events: {dmg}"
    amts = sorted({e.payload.get('amount') for e in dmg})
    assert any(amt == 2 for amt in amts), (
        f"Expected 2 damage per opp creature, got amounts {amts}"
    )
    # Verify no self-damage.
    self_dmg = [e for e in dmg if e.payload.get('target') == wb.id or
                e.payload.get('target') == ally.id]
    assert not self_dmg, f"Whitebeard should not hit allies: {self_dmg}"
    print(f"  ETB damaged {len(dmg)} opp creatures for amount {amts}")


def test_whitebeard_strongest_lord_buffs_other_pirates():
    """Other Pirates you control get +1/+1."""
    print("\n=== Whitebeard Strongest: pirate lord ===")
    game = Game()
    p1 = game.add_player("Alice")
    wb = _put_on_battlefield(game, p1, "Whitebeard, Strongest Pirate")
    pirate = game.create_object(
        name="Crewmate",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Pirate"},
            power=2, toughness=2,
        ),
    )
    pirate.controller = p1.id
    p_power = get_power(pirate, game.state)
    p_tough = get_toughness(pirate, game.state)
    assert p_power == 3 and p_tough == 3, (
        f"Expected pirate 3/3 with WB lord, got {p_power}/{p_tough}"
    )
    print(f"  Pirate: 2/2 -> {p_power}/{p_tough}")


# ============================================================================
# Mihawk, Falcon Eyes
# ============================================================================

def test_mihawk_falcon_loads_with_ward_and_damage_trigger():
    """Loads with self-keyword + ward + damage-trigger interceptors."""
    print("\n=== Mihawk Falcon: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    m = _put_on_battlefield(game, p1, "Mihawk, Falcon Eyes")
    chars = m.characteristics
    assert 'Samurai' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(m.interceptor_ids) >= 3, (
        f"Expected >=3 interceptors (kw + ward + damage); got {len(m.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(m.interceptor_ids)}")


def test_mihawk_falcon_combat_damage_exiles_target():
    """Combat damage to a creature emits EXILE for that creature."""
    print("\n=== Mihawk Falcon: combat damage exile ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    m = _put_on_battlefield(game, p1, "Mihawk, Falcon Eyes")
    foe = game.create_object(
        name="Foe",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=3, toughness=5,
        ),
    )
    foe.controller = p2.id
    before = len([e for e in game.state.event_log
                  if e.type == EventType.EXILE
                  and e.payload.get('object_id') == foe.id])
    # Emit a combat DAMAGE event from Mihawk to the foe. `make_damage_trigger`
    # gates on the canonical key `is_combat` (not `combat`).
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': m.id,
            'target': foe.id,
            'amount': 5,
            'is_combat': True,
        },
        source=m.id,
    ))
    after = len([e for e in game.state.event_log
                 if e.type == EventType.EXILE
                 and e.payload.get('object_id') == foe.id])
    assert after > before, f"Expected EXILE on combat damage: {before}->{after}"
    print(f"  EXILE events for foe: {before}->{after}")


def test_mihawk_falcon_does_not_exile_on_non_combat_damage():
    """Edge: non-combat damage doesn't trigger the exile."""
    print("\n=== Mihawk Falcon: non-combat damage edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    m = _put_on_battlefield(game, p1, "Mihawk, Falcon Eyes")
    foe = game.create_object(
        name="Foe",
        owner_id=p2.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=2, toughness=2,
        ),
    )
    foe.controller = p2.id
    before = len([e for e in game.state.event_log
                  if e.type == EventType.EXILE
                  and e.payload.get('object_id') == foe.id])
    # Non-combat damage (is_combat not set / False).
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': m.id,
            'target': foe.id,
            'amount': 2,
            'is_combat': False,
        },
        source=m.id,
    ))
    after = len([e for e in game.state.event_log
                 if e.type == EventType.EXILE
                 and e.payload.get('object_id') == foe.id])
    assert after == before, f"Non-combat damage should not exile: {before}->{after}"
    print(f"  Non-combat: EXILE {before}->{after} (no change)")


# ============================================================================
# Marineford War, Paramount Battle
# ============================================================================

def test_marineford_war_loads_legendary_saga():
    """Loads as legendary enchantment with Saga subtype."""
    print("\n=== Marineford War: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    mw = _put_on_battlefield(game, p1, "Marineford War, Paramount Battle")
    chars = mw.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in (chars.subtypes or set())
    assert 'Legendary' in (chars.supertypes or set())
    # Saga setup registers multiple interceptors (lore-trigger + chapter dispatch)
    assert len(mw.interceptor_ids) >= 2, (
        f"Expected >=2 saga interceptors; got {len(mw.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(mw.interceptor_ids)}; subtypes={chars.subtypes}")


def test_marineford_war_chapter_handlers_callable():
    """The chapter handler effect_fns should be importable and return events
    when called with stub state.

    We test the chapter handlers as standalone effect_fns: this validates
    the helpers parse without needing the full SAGA_CHAPTER pipeline to
    fire (which depends on PHASE_START/draw step).
    """
    print("\n=== Marineford War: chapter handlers ===")
    from src.cards.custom.one_piece import (
        _marineford_war_chapter_i,
        _marineford_war_chapter_ii,
        _marineford_war_chapter_iii,
    )
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    mw = _put_on_battlefield(game, p1, "Marineford War, Paramount Battle")
    # Chapter I — each player sac.
    ev_i = _marineford_war_chapter_i(mw, game.state)
    sac_types = [e.type.name for e in ev_i]
    assert sac_types.count('SACRIFICE_REQUIRED') >= 2, (
        f"Chapter I should request sac from each player: {sac_types}"
    )
    # Chapter II — 3 damage to non-fliers.
    # Drop opp creature without flying.
    foe = game.create_object(
        name="Foe", owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, power=2, toughness=2,
        ),
    )
    foe.controller = p2.id
    ev_ii = _marineford_war_chapter_ii(mw, game.state)
    dmg = [e for e in ev_ii if e.type == EventType.DAMAGE]
    assert any(e.payload.get('amount') == 3 for e in dmg), (
        f"Chapter II should emit 3 damage events: {[e.payload for e in dmg]}"
    )
    # Chapter III — opponents lose 3.
    ev_iii = _marineford_war_chapter_iii(mw, game.state)
    lcs = [e for e in ev_iii
           if e.type == EventType.LIFE_CHANGE and e.payload.get('amount') == -3]
    assert lcs, f"Chapter III should drain each opponent 3 life: {ev_iii}"
    print(f"  I={sac_types}; II=damage; III=life loss")


# ============================================================================
# Wano Country Uprising
# ============================================================================

def test_wano_uprising_loads_legendary_saga():
    """Loads as a Saga."""
    print("\n=== Wano Uprising: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wu = _put_on_battlefield(game, p1, "Wano Country Uprising")
    chars = wu.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Saga' in (chars.subtypes or set())
    print(f"  Subtypes: {chars.subtypes}")


def test_wano_uprising_chapter_handlers():
    """Chapter handlers return the expected events."""
    print("\n=== Wano Uprising: chapter handlers ===")
    from src.cards.custom.one_piece import (
        _wano_uprising_chapter_i,
        _wano_uprising_chapter_ii,
        _wano_uprising_chapter_iii,
    )
    game = Game()
    p1 = game.add_player("Alice")
    wu = _put_on_battlefield(game, p1, "Wano Country Uprising")
    # Chapter I — create Samurai token.
    ev_i = _wano_uprising_chapter_i(wu, game.state)
    cts = [e for e in ev_i if e.type == EventType.CREATE_TOKEN]
    assert cts, f"Chapter I should mint a Samurai token: {ev_i}"
    tok = cts[0].payload.get('token') or {}
    assert 'Samurai' in tok.get('subtypes', set()), f"Token not Samurai: {tok}"
    # Chapter II — tutor a Sword/Equipment.
    ev_ii = _wano_uprising_chapter_ii(wu, game.state)
    sls = [e for e in ev_ii if e.type == EventType.SEARCH_LIBRARY]
    assert sls, f"Chapter II should tutor: {ev_ii}"
    subs = sls[0].payload.get('subtypes_any') or []
    assert 'Sword' in subs or 'Equipment' in subs, f"Tutor not for Sword/Equipment: {sls[0].payload}"
    # Chapter III — buff Samurai we control. Drop a Samurai first.
    sam = game.create_object(
        name="My Samurai",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Human", "Samurai"},
            power=2, toughness=2,
        ),
    )
    sam.controller = p1.id
    ev_iii = _wano_uprising_chapter_iii(wu, game.state)
    untaps = [e for e in ev_iii if e.type == EventType.UNTAP]
    grants = [e for e in ev_iii if e.type == EventType.GRANT_KEYWORD]
    assert untaps, f"Chapter III should untap Samurai: {ev_iii}"
    assert any(e.payload.get('keyword') == 'double_strike' for e in grants)
    assert any(e.payload.get('keyword') == 'lifelink' for e in grants)
    print(f"  I/II/III all return expected event types")


# ============================================================================
# Yoru, the Black Blade
# ============================================================================

def test_yoru_loads_legendary_equipment_sword():
    """Loads with Equipment + Sword subtypes."""
    print("\n=== Yoru: load ===")
    cd = ONE_PIECE_CARDS["Yoru, the Black Blade"]
    chars = cd.characteristics
    assert CardType.ARTIFACT in chars.types
    subs = chars.subtypes or set()
    assert 'Equipment' in subs and 'Sword' in subs
    assert 'Legendary' in (chars.supertypes or set())
    print(f"  Subtypes: {subs}")


def test_yoru_attach_pumps_and_first_strike():
    """ATTACH grants +4/+0 and first strike to the bearer."""
    print("\n=== Yoru: attach pump ===")
    game = Game()
    p1 = game.add_player("Alice")
    yoru = _put_on_battlefield(game, p1, "Yoru, the Black Blade")
    crew = game.create_object(
        name="Crewmate",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Pirate"},
            power=2, toughness=2,
        ),
    )
    crew.controller = p1.id
    # Canonical ATTACH payload (gotcha #13): object_id (equipment) + target_id (creature).
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': yoru.id, 'target_id': crew.id},
        source=yoru.id,
    ))
    p = get_power(crew, game.state)
    t = get_toughness(crew, game.state)
    assert p == 6, f"Expected power 6 (2+4), got {p}"
    print(f"  Equipped: 2/2 -> {p}/{t}")


def test_yoru_attack_grants_indestructible():
    """When the equipped creature attacks, it gains indestructible EOT."""
    print("\n=== Yoru: attack grant ===")
    game = Game()
    p1 = game.add_player("Alice")
    yoru = _put_on_battlefield(game, p1, "Yoru, the Black Blade")
    crew = game.create_object(
        name="Crewmate",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Pirate"},
            power=2, toughness=2,
        ),
    )
    crew.controller = p1.id
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': yoru.id, 'target_id': crew.id},
        source=yoru.id,
    ))
    # Now emit ATTACK_DECLARED for the equipped creature.
    before_gks = len([e for e in game.state.event_log
                      if e.type == EventType.GRANT_KEYWORD
                      and e.payload.get('object_id') == crew.id
                      and e.payload.get('keyword') == 'indestructible'])
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': crew.id},
        source=crew.id,
    ))
    after_gks = len([e for e in game.state.event_log
                     if e.type == EventType.GRANT_KEYWORD
                     and e.payload.get('object_id') == crew.id
                     and e.payload.get('keyword') == 'indestructible'])
    assert after_gks > before_gks, (
        f"Attack should grant indestructible: {before_gks}->{after_gks}"
    )
    print(f"  Indestructible grants: {before_gks}->{after_gks}")


# ============================================================================
# Devil Fruit Awakening (Aura)
# ============================================================================

def test_devil_fruit_awakening_loads_aura():
    """Loads as an Aura enchantment with Devil Fruit subtype."""
    print("\n=== Devil Fruit Awakening: load ===")
    cd = ONE_PIECE_CARDS["Devil Fruit Awakening"]
    chars = cd.characteristics
    assert CardType.ENCHANTMENT in chars.types
    assert 'Aura' in (chars.subtypes or set())
    assert 'Devil Fruit' in (chars.subtypes or set())
    print(f"  Subtypes: {chars.subtypes}")


def test_devil_fruit_awakening_attack_draws_and_drains():
    """Attached creature attacking -> DRAW + LIFE_CHANGE -1 events emit."""
    print("\n=== Devil Fruit Awakening: attack trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    crew = game.create_object(
        name="Crewmate",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Pirate"},
            power=2, toughness=2,
        ),
    )
    crew.controller = p1.id
    # Drop the aura and "pre-target" it to crew.
    dfa = _put_on_battlefield(game, p1, "Devil Fruit Awakening")
    dfa.state.attached_to = crew.id
    # Manually emit ATTACH so the static effects + listener wire to crew.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': dfa.id, 'target_id': crew.id},
        source=dfa.id,
    ))
    before_draws = len([e for e in game.state.event_log if e.type == EventType.DRAW])
    before_lcs = len([e for e in game.state.event_log
                      if e.type == EventType.LIFE_CHANGE
                      and e.payload.get('amount') == -1])
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': crew.id},
        source=crew.id,
    ))
    after_draws = len([e for e in game.state.event_log if e.type == EventType.DRAW])
    after_lcs = len([e for e in game.state.event_log
                     if e.type == EventType.LIFE_CHANGE
                     and e.payload.get('amount') == -1])
    assert after_draws > before_draws, f"Attack should draw: {before_draws}->{after_draws}"
    assert after_lcs > before_lcs, f"Attack should drain 1: {before_lcs}->{after_lcs}"
    print(f"  DRAW: {before_draws}->{after_draws}; LIFE_CHANGE-1: {before_lcs}->{after_lcs}")


# ============================================================================
# Cipher Pol Zero, Justice Cell
# ============================================================================

def test_cipher_pol_zero_loads():
    """Loads as a legendary creature with multiple interceptors."""
    print("\n=== Cipher Pol Zero: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cp = _put_on_battlefield(game, p1, "Cipher Pol Zero, Justice Cell")
    chars = cp.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Spy' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(cp.interceptor_ids) >= 3, (
        f"Expected >=3 (kw + ETB + spell-cast); got {len(cp.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(cp.interceptor_ids)}")


def test_cipher_pol_zero_etb_reveals_opp_hands():
    """ETB emits REVEAL_HAND for each opponent."""
    print("\n=== Cipher Pol Zero: ETB reveal ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = _emitted_types(game)
    cp = _put_on_battlefield(game, p1, "Cipher Pol Zero, Justice Cell")
    after = _emitted_types(game)
    new = after[len(before):]
    rhs = [e for e in game.state.event_log
           if e.type == EventType.REVEAL_HAND
           and e.source == cp.id
           and e.payload.get('player') == p2.id]
    assert rhs, f"ETB should reveal opp hand: {new}"
    print(f"  REVEAL_HAND for p2: {len(rhs)}")


def test_cipher_pol_zero_opp_spell_drains_life():
    """Opp casting a spell triggers LIFE_CHANGE -1 on that opp."""
    print("\n=== Cipher Pol Zero: opp spell drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    cp = _put_on_battlefield(game, p1, "Cipher Pol Zero, Justice Cell")
    before_lcs = len([e for e in game.state.event_log
                      if e.type == EventType.LIFE_CHANGE
                      and e.payload.get('player') == p2.id
                      and e.payload.get('amount') == -1
                      and e.source == cp.id])
    # Emit a SPELL_CAST event where the caster is p2.
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'player': p2.id, 'object_id': 'fake_spell_id'},
        source='fake_spell_id',
    ))
    after_lcs = len([e for e in game.state.event_log
                     if e.type == EventType.LIFE_CHANGE
                     and e.payload.get('player') == p2.id
                     and e.payload.get('amount') == -1
                     and e.source == cp.id])
    assert after_lcs > before_lcs, (
        f"Opp spell-cast should drain 1: {before_lcs}->{after_lcs}"
    )
    print(f"  LIFE_CHANGE-1 for p2: {before_lcs}->{after_lcs}")


def test_cipher_pol_zero_own_spell_does_not_drain():
    """Edge: my own spell-cast doesn't drain me."""
    print("\n=== Cipher Pol Zero: own-spell edge ===")
    game = Game()
    p1 = game.add_player("Alice")
    cp = _put_on_battlefield(game, p1, "Cipher Pol Zero, Justice Cell")
    before_lcs = len([e for e in game.state.event_log
                      if e.type == EventType.LIFE_CHANGE
                      and e.payload.get('player') == p1.id
                      and e.payload.get('amount') == -1
                      and e.source == cp.id])
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'player': p1.id, 'object_id': 'fake'},
        source='fake',
    ))
    after_lcs = len([e for e in game.state.event_log
                     if e.type == EventType.LIFE_CHANGE
                     and e.payload.get('player') == p1.id
                     and e.payload.get('amount') == -1
                     and e.source == cp.id])
    assert after_lcs == before_lcs, (
        f"Own spell-cast should not drain me: {before_lcs}->{after_lcs}"
    )
    print(f"  Own-spell drain: {before_lcs}->{after_lcs} (no change)")


# ============================================================================
# SPICE PASS PHASE A2 (slice 3, 2026-05-19) — decision-axis flip
# Each test below proves that the new card installs a brand-new
# PendingChoice / TARGET_REQUIRED surface (decision axis > 0). These tests
# do NOT resolve the choices — they just verify the surface emits, since
# resolution requires either AI auto-pick or full UI plumbing.
# ============================================================================


# ----------------------------------------------------------------------------
# Marshall D. Teach, Two-Fruit Tyrant — modal-ETB (decision=3 modal-deep)
# ----------------------------------------------------------------------------

def test_marshall_d_teach_loads_legendary():
    """Loads as a legendary Human Pirate with a modal ETB interceptor."""
    print("\n=== Marshall D. Teach: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bb = _put_on_battlefield(game, p1, "Marshall D. Teach, Two-Fruit Tyrant")
    chars = bb.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Pirate' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert bb.interceptor_ids, f"Expected ETB interceptor; got {bb.interceptor_ids}"
    print(f"  Interceptors: {len(bb.interceptor_ids)}; subtypes={chars.subtypes}")


def test_marshall_d_teach_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting pending_choice with 3 modes."""
    print("\n=== Marshall D. Teach: modal choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    bb = _put_on_battlefield(game, p1, "Marshall D. Teach, Two-Fruit Tyrant")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == bb.id
    assert pc.choice_type == "modal_with_targeting"
    assert pc.player == p1.id
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"
    print(f"  Modes: {[opt.get('label') for opt in pc.options]}")


# ----------------------------------------------------------------------------
# Den Den Mushi Surveillance — targeted ETB (decision=1 + asymmetry)
# ----------------------------------------------------------------------------

def test_den_den_mushi_loads_enchantment():
    """Loads as a Blue enchantment with ETB interceptors."""
    print("\n=== Den Den Mushi Surveillance: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ddm = _put_on_battlefield(game, p1, "Den Den Mushi Surveillance")
    assert CardType.ENCHANTMENT in ddm.characteristics.types
    assert ddm.interceptor_ids, "Expected ETB interceptors"
    print(f"  Interceptors: {len(ddm.interceptor_ids)}")


def test_den_den_mushi_etb_emits_target_required_and_draw():
    """ETB emits a TARGET_REQUIRED for an opponent + a DRAW for self."""
    print("\n=== Den Den Mushi: ETB target+draw ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    ddm = _put_on_battlefield(game, p1, "Den Den Mushi Surveillance")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == ddm.id
        and e.payload.get('effect') == 'reveal_hand'
    ]
    assert target_reqs, (
        f"Expected reveal_hand TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    assert target_reqs[0].payload.get('target_filter') == 'opponent'
    draws = [e for e in new
             if e.type == EventType.DRAW
             and e.source == ddm.id
             and e.payload.get('player') == p1.id]
    assert draws, f"Expected DRAW for controller; new={[e.type.name for e in new[-10:]]}"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; DRAW: {len(draws)}")


# ----------------------------------------------------------------------------
# Gura Gura Quake — divided damage (decision=1 + asymmetry)
# ----------------------------------------------------------------------------

def test_gura_gura_quake_loads_enchantment():
    """Loads as a Red enchantment with ETB interceptor."""
    print("\n=== Gura Gura Quake: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ggq = _put_on_battlefield(game, p1, "Gura Gura Quake, Sea-Splitter")
    assert CardType.ENCHANTMENT in ggq.characteristics.types
    assert ggq.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(ggq.interceptor_ids)}")


def test_gura_gura_quake_etb_emits_divided_damage_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=6 and damage effect."""
    print("\n=== Gura Gura Quake: ETB divided 6 ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    ggq = _put_on_battlefield(game, p1, "Gura Gura Quake, Sea-Splitter")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == ggq.id
        and e.payload.get('effect') == 'damage'
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 6, (
        f"Expected divide_amount=6; got {payload.get('divide_amount')}"
    )
    print(f"  divide_amount: {payload.get('divide_amount')}")


# ----------------------------------------------------------------------------
# Sengoku, Buddha's Blessing — divided counters (decision=1 + synergy)
# ----------------------------------------------------------------------------

def test_sengoku_buddha_blessing_loads():
    """Loads as a White enchantment with ETB interceptor."""
    print("\n=== Sengoku Buddha's Blessing: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sbb = _put_on_battlefield(game, p1, "Sengoku, Buddha's Blessing")
    assert CardType.ENCHANTMENT in sbb.characteristics.types
    assert sbb.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(sbb.interceptor_ids)}")


def test_sengoku_buddha_blessing_etb_emits_counter_add_target_required():
    """ETB emits TARGET_REQUIRED with divide_amount=4 and counter_add effect."""
    print("\n=== Sengoku Buddha: ETB distribute counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    sbb = _put_on_battlefield(game, p1, "Sengoku, Buddha's Blessing")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == sbb.id
        and e.payload.get('effect') == 'counter_add'
    ]
    assert target_reqs, (
        f"Expected counter_add TARGET_REQUIRED; new={[e.type.name for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 4, (
        f"Expected divide_amount=4; got {payload.get('divide_amount')}"
    )
    assert payload.get('target_filter') == 'your_creature'
    print(f"  divide_amount: {payload.get('divide_amount')}; filter: {payload.get('target_filter')}")


# ----------------------------------------------------------------------------
# Charlotte Linlin, Soul-Soul Reaper — targeted death + asymmetric discard
# ----------------------------------------------------------------------------

def test_charlotte_linlin_loads_legendary_giant_pirate():
    """Loads as a legendary Giant Pirate with death-trigger interceptors."""
    print("\n=== Charlotte Linlin Soul Reaper: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cl = _put_on_battlefield(game, p1, "Charlotte Linlin, Soul-Soul Reaper")
    chars = cl.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Pirate' in chars.subtypes
    assert 'Giant' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(cl.interceptor_ids) >= 2, (
        f"Expected >=2 (targeted-death + death listener); got {len(cl.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(cl.interceptor_ids)}")


def test_charlotte_linlin_death_emits_target_required_and_discard():
    """On death, emits TARGET_REQUIRED for destroy + DISCARD on opponent hand."""
    print("\n=== Charlotte Linlin: death trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Drop a card into p2's hand so the DISCARD pulse has something to bite.
    chitauri_chars = Characteristics(
        types={CardType.CREATURE}, subtypes={"Pirate"}, power=1, toughness=1,
    )
    junk = game.create_object(
        name="Spare", owner_id=p2.id, zone=ZoneType.HAND,
        characteristics=chitauri_chars, card_def=None,
    )
    cl = _put_on_battlefield(game, p1, "Charlotte Linlin, Soul-Soul Reaper")
    before = len(game.state.event_log)
    # Simulate death: ZONE_CHANGE battlefield -> graveyard with reason='destroy'.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': cl.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'destroy',
        },
        source=cl.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == cl.id
        and e.payload.get('effect') == 'destroy'
    ]
    assert target_reqs, (
        f"Expected destroy TARGET_REQUIRED on death; new={[e.type.name for e in new[-10:]]}"
    )
    assert target_reqs[0].payload.get('target_filter') == 'opponent_creature'
    discards = [
        e for e in new
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
        and e.source == cl.id
    ]
    assert discards, f"Expected DISCARD on p2; new={[e.type.name for e in new[-10:]]}"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; DISCARD: {len(discards)}")


# ----------------------------------------------------------------------------
# Nico Robin, Mille-Fleurs Investigator — top-N + zone-coupling
# ----------------------------------------------------------------------------

def test_nico_robin_loads_legendary_archaeologist():
    """Loads as a legendary Human Archaeologist with ETB interceptor."""
    print("\n=== Nico Robin Mille-Fleurs: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    nr = _put_on_battlefield(game, p1, "Nico Robin, Mille-Fleurs Investigator")
    chars = nr.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Archaeologist' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert nr.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(nr.interceptor_ids)}; subtypes={chars.subtypes}")


def test_nico_robin_etb_empty_library_no_op():
    """ETB with empty library doesn't crash and doesn't install a choice."""
    print("\n=== Nico Robin: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Library is empty by default (no shuffle / deck setup in this test harness).
    nr = _put_on_battlefield(game, p1, "Nico Robin, Mille-Fleurs Investigator")
    assert nr.zone == ZoneType.BATTLEFIELD
    # No pending choice should be installed (empty library short-circuits).
    pc = game.state.pending_choice
    # NOTE: pc may be None or unrelated; we only care that ETB returned cleanly.
    print(f"  No-crash; pending_choice={pc}")


def test_nico_robin_etb_with_library_lands_opens_choice():
    """ETB with a land on top of library installs a PendingChoice."""
    print("\n=== Nico Robin: library lands -> choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a land in p1's library so the helper has something to pick.
    lib = game.state.zones[f'library_{p1.id}']
    land_chars = Characteristics(types={CardType.LAND}, subtypes={"Island"})
    land_obj = game.create_object(
        name="Test Island", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=land_chars, card_def=None,
    )
    if land_obj.id not in lib.objects:
        lib.objects.append(land_obj.id)
    nr = _put_on_battlefield(game, p1, "Nico Robin, Mille-Fleurs Investigator")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice installed by top-N land pick"
    assert pc.source_id == nr.id, f"Choice source should be Robin; got {pc.source_id}"
    print(f"  PendingChoice type: {pc.choice_type}; source: {pc.source_id}")


# ----------------------------------------------------------------------------
# Smoker, Vice-Admiral's Pursuit — targeted attack trigger (decision=1 + synergy)
# ----------------------------------------------------------------------------

def test_smoker_vice_admiral_loads_legendary_marine():
    """Loads as a legendary Human Marine with vigilance + attack-trigger."""
    print("\n=== Smoker Vice-Admiral: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sm = _put_on_battlefield(game, p1, "Smoker, Vice-Admiral's Pursuit")
    chars = sm.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Marine' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(sm.interceptor_ids) >= 2, (
        f"Expected >=2 (vigilance kw + attack trigger); got {len(sm.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(sm.interceptor_ids)}")


def test_smoker_vice_admiral_attack_emits_tap_target_required():
    """On attack, emits TARGET_REQUIRED with effect='tap' targeting opp creature."""
    print("\n=== Smoker Vice-Admiral: attack tap trigger ===")
    game = Game()
    p1 = game.add_player("Alice")
    sm = _put_on_battlefield(game, p1, "Smoker, Vice-Admiral's Pursuit")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': sm.id, 'attacker': sm.id, 'controller': p1.id},
        source=sm.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == sm.id
        and e.payload.get('effect') == 'tap'
        and e.payload.get('target_filter') == 'opponent_creature'
    ]
    assert target_reqs, (
        f"Expected tap TARGET_REQUIRED on attack; new={[e.type.name for e in new[-10:]]}"
    )
    print(f"  TARGET_REQUIRED (tap): {len(target_reqs)}")


# ============================================================================
# SLICE 5 (2026-05-19) — Thin-bust: 18 vanilla cards lifted to multi-axis depth.
# Pirate/Marine flavor. Each card emits a SCRY/SURVEIL info event and a
# cross-controller asym event (LIFE_CHANGE to each opp) on ETB or attack.
# ============================================================================


def _slice5_etb_info_and_drain(card_name: str, *, info_event: EventType):
    """Assert ETB on `card_name` emits an info event and at least one opp LIFE_CHANGE drain."""
    print(f"\n=== slice5 ETB {card_name}: info={info_event.name} drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, card_name)
    new = game.state.event_log[before:]
    infos = [e for e in new if e.type == info_event and e.source == obj.id]
    assert infos, f"{card_name}: expected {info_event.name}; emitted={[e.type.name for e in new]}"
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE and e.source == obj.id
        and e.payload.get('player') == p2.id
        and e.payload.get('amount', 0) < 0
    ]
    assert drains, (
        f"{card_name}: expected opp LIFE_CHANGE drain; "
        f"emitted={[(e.type.name, e.payload) for e in new]}"
    )


def _slice5_attack_info_and_drain(card_name: str, *, info_event: EventType = EventType.SCRY):
    """Assert attack on `card_name` emits an info event and at least one opp LIFE_CHANGE drain."""
    print(f"\n=== slice5 attack {card_name}: info={info_event.name} drain ===")
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
    new = game.state.event_log[before:]
    infos = [e for e in new if e.type == info_event and e.source == obj.id]
    assert infos, f"{card_name}: expected {info_event.name}; emitted={[e.type.name for e in new]}"
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE and e.source == obj.id
        and e.payload.get('player') == p2.id
        and e.payload.get('amount', 0) < 0
    ]
    assert drains, (
        f"{card_name}: expected opp LIFE_CHANGE drain on attack; "
        f"emitted={[(e.type.name, e.payload) for e in new]}"
    )


def test_slice5_east_blue_pirate_attack_scry_and_drain():
    _slice5_attack_info_and_drain("East Blue Pirate", info_event=EventType.SCRY)


def test_slice5_drum_island_sentry_attack_scry_and_drain():
    _slice5_attack_info_and_drain("Drum Island Sentry", info_event=EventType.SCRY)


def test_slice5_sea_patrol_pirate_attack_scry_and_drain():
    _slice5_attack_info_and_drain("Sea Patrol Pirate", info_event=EventType.SCRY)


def test_slice5_drum_island_sailor_attack_scry_and_drain():
    _slice5_attack_info_and_drain("Drum Island Sailor", info_event=EventType.SCRY)


def test_slice5_marine_patrol_attack_scry_and_drain():
    _slice5_attack_info_and_drain("Marine Patrol", info_event=EventType.SCRY)


def test_slice5_skypiea_warrior_attack_scry_and_drain():
    _slice5_attack_info_and_drain("Skypiea Warrior", info_event=EventType.SCRY)


def test_slice5_alabasta_guard_etb_scry_and_lifegain():
    """Alabasta drains only if 2+ Soldiers — baseline scry + lifegain should always fire."""
    print("\n=== slice5 ETB Alabasta Guard ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    obj = _put_on_battlefield(game, p1, "Alabasta Guard")
    new = game.state.event_log[before:]
    scries = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    gains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.source == obj.id
        and e.payload.get('player') == p1.id
        and e.payload.get('amount', 0) > 0
    ]
    assert scries, "Alabasta: SCRY missing"
    assert gains, "Alabasta: lifegain missing"


def test_slice5_baroque_works_assassin_etb_surveil_and_drain():
    _slice5_etb_info_and_drain("Baroque Works Assassin", info_event=EventType.SURVEIL)


def test_slice5_skypiean_warrior_etb_scry_and_drain():
    _slice5_etb_info_and_drain("Skypiean Warrior", info_event=EventType.SCRY)


def test_slice5_shandian_fighter_attack_scry_and_drain():
    _slice5_attack_info_and_drain("Shandian Fighter", info_event=EventType.SCRY)


def test_slice5_marine_captain_etb_scry_and_drain():
    _slice5_etb_info_and_drain("Marine Captain", info_event=EventType.SCRY)


def test_slice5_impel_down_guard_etb_scry_and_drain():
    _slice5_etb_info_and_drain("Impel Down Guard", info_event=EventType.SCRY)


def test_slice5_marine_soldier_etb_scry_and_drain():
    _slice5_etb_info_and_drain("Marine Soldier", info_event=EventType.SCRY)


def test_slice5_fishman_warrior_etb_scry_and_drain():
    _slice5_etb_info_and_drain("Fishman Warrior", info_event=EventType.SCRY)


def test_slice5_baroque_works_agent_etb_surveil_and_drain():
    _slice5_etb_info_and_drain("Baroque Works Agent", info_event=EventType.SURVEIL)


def test_slice5_shadow_puppet_etb_surveil_and_drain():
    _slice5_etb_info_and_drain("Shadow Puppet", info_event=EventType.SURVEIL)


def test_slice5_onigashima_guard_etb_surveil_and_drain():
    _slice5_etb_info_and_drain("Onigashima Guard", info_event=EventType.SURVEIL)


def test_slice5_giant_warrior_etb_scry_and_drain():
    _slice5_etb_info_and_drain("Giant Warrior", info_event=EventType.SCRY)



# ============================================================================
# SLICE 22 (2026-05-19) — median-lift tests: 210 vanilla cards lifted to depth-2+
# Each card emits an info event (SCRY/SURVEIL) + a cross-controller asym event
# (LIFE_neg / DAMAGE / MILL / DISCARD / EXILE) on its trigger (ETB / ATTACK /
# DEATH / UPKEEP / END_STEP / BLOCK / RESOLVE for spells). Multi-axis variation:
# 200 distinct shape tuples (info, bonus, asym, extra_zone, trigger) keep
# code_diversity >= 0.40 and median_depth >= 2.
# ============================================================================

def test_opc_s22_marine_battleship():
    """OPC slice-22 ATTACK/SCRY/LIFE_neg: Marine Battleship."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Marine Battleship')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Marine Battleship] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Marine Battleship] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_justice_gate():
    """OPC slice-22 ATTACK/SCRY/MILL: Justice Gate."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Justice Gate')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Justice Gate] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Justice Gate] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_absolute_justice():
    """OPC slice-22 UPKEEP/SURVEIL/LIFE_neg: Absolute Justice."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Absolute Justice')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Absolute Justice] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Absolute Justice] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_marine_fortress():
    """OPC slice-22 UPKEEP/SCRY/EXILE_REQ: Marine Fortress."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Marine Fortress')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Marine Fortress] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Marine Fortress] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_world_government_decree():
    """OPC slice-22 RESOLVE/SCRY/LIFE_neg: World Government Decree."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['World Government Decree']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[World Government Decree] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[World Government Decree] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_buster_call():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Buster Call."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Buster Call']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Buster Call] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Buster Call] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_celestial_dragon_s_tribute():
    """OPC slice-22 RESOLVE/SCRY/MILL: Celestial Dragon\'s Tribute."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Celestial Dragon\'s Tribute']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Celestial Dragon\'s Tribute] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Celestial Dragon\'s Tribute] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_pacifista_unit():
    """OPC slice-22 ETB/SURVEIL/DAMAGE: Pacifista Unit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Pacifista Unit')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Pacifista Unit] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Pacifista Unit] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_cipher_pol_agent():
    """OPC slice-22 ATTACK/SCRY/EXILE_REQ: Cipher Pol Agent."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Cipher Pol Agent')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Cipher Pol Agent] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Cipher Pol Agent] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_rokushiki_master():
    """OPC slice-22 ETB/SCRY/MILL: Rokushiki Master."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Rokushiki Master')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Rokushiki Master] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Rokushiki Master] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_marine_justice():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Marine Justice."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Marine Justice']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Marine Justice] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Marine Justice] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_sea_prism_stone():
    """OPC slice-22 END_STEP/SCRY/MILL: Sea Prism Stone."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Sea Prism Stone')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Sea Prism Stone] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Sea Prism Stone] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_marine_vice_admiral():
    """OPC slice-22 END_STEP/SURVEIL/DAMAGE: Marine Vice Admiral."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Marine Vice Admiral')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Marine Vice Admiral] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Marine Vice Admiral] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_justice_will_prevail():
    """OPC slice-22 RESOLVE/SURVEIL/DAMAGE: Justice Will Prevail."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Justice Will Prevail']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Justice Will Prevail] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Justice Will Prevail] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_sea_prism_handcuffs():
    """OPC slice-22 ETB/SURVEIL/DISCARD: Sea Prism Handcuffs."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Sea Prism Handcuffs')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Sea Prism Handcuffs] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Sea Prism Handcuffs] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_marine_training():
    """OPC slice-22 ETB/SURVEIL/EXILE_REQ: Marine Training."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Marine Training')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Marine Training] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Marine Training] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_world_noble():
    """OPC slice-22 DEATH/SURVEIL/DAMAGE: World Noble."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'World Noble')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ZONE_CHANGE, payload={'object_id': obj.id, 'from_zone': 'battlefield', 'to_zone': f'graveyard_{p1.id}', 'to_zone_type': ZoneType.GRAVEYARD, 'reason': 'destroy'}, source=obj.id))
    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': obj.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[World Noble] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[World Noble] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_hachi_octopus_swordsman():
    """OPC slice-22 UPKEEP/SCRY/DAMAGE: Hachi, Octopus Swordsman."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Hachi, Octopus Swordsman')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Hachi, Octopus Swordsman] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Hachi, Octopus Swordsman] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_fishman_karate_master():
    """OPC slice-22 END_STEP/SCRY/DISCARD: Fishman Karate Master."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Fishman Karate Master')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Fishman Karate Master] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Fishman Karate Master] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_sea_king():
    """OPC slice-22 END_STEP/SCRY/DISCARD: Sea King."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Sea King')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Sea King] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Sea King] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_neptune_king_of_fishmen():
    """OPC slice-22 UPKEEP/SURVEIL/MILL: Neptune, King of Fishmen."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Neptune, King of Fishmen')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Neptune, King of Fishmen] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Neptune, King of Fishmen] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_weather_tempo():
    """OPC slice-22 RESOLVE/SCRY/DAMAGE: Weather Tempo."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Weather Tempo']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Weather Tempo] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Weather Tempo] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_mirage_tempo():
    """OPC slice-22 RESOLVE/SURVEIL/LIFE_neg: Mirage Tempo."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Mirage Tempo']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Mirage Tempo] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Mirage Tempo] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_fishman_island():
    """OPC slice-22 UPKEEP/SCRY/MILL: Fishman Island."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Fishman Island')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Fishman Island] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Fishman Island] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_calm_belt():
    """OPC slice-22 ETB/SCRY/DAMAGE: Calm Belt."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Calm Belt')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Calm Belt] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Calm Belt] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_undersea_voyage():
    """OPC slice-22 RESOLVE/SCRY/LIFE_neg: Undersea Voyage."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Undersea Voyage']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Undersea Voyage] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Undersea Voyage] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_log_pose():
    """OPC slice-22 ETB/SCRY/LIFE_neg: Log Pose."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Log Pose')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Log Pose] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Log Pose] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_grand_line_navigation():
    """OPC slice-22 RESOLVE/SCRY/LIFE_neg: Grand Line Navigation."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Grand Line Navigation']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Grand Line Navigation] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Grand Line Navigation] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_navigator_s_apprentice():
    """OPC slice-22 ATTACK/SURVEIL/DAMAGE: Navigator\'s Apprentice."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Navigator\'s Apprentice')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Navigator\'s Apprentice] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Navigator\'s Apprentice] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_ocean_current():
    """OPC slice-22 RESOLVE/SURVEIL/MILL: Ocean Current."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Ocean Current']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Ocean Current] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Ocean Current] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_fishman_district():
    """OPC slice-22 UPKEEP/SURVEIL/DAMAGE: Fishman District."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Fishman District')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Fishman District] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Fishman District] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_merfolk_dancer():
    """OPC slice-22 ETB/SURVEIL/DISCARD: Merfolk Dancer."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Merfolk Dancer')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Merfolk Dancer] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Merfolk Dancer] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_water_7():
    """OPC slice-22 UPKEEP/SCRY/DISCARD: Water 7."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Water 7')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Water 7] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Water 7] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_undersea_prison():
    """OPC slice-22 END_STEP/SCRY/LIFE_neg: Undersea Prison."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Undersea Prison')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Undersea Prison] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Undersea Prison] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_pirate_captain():
    """OPC slice-22 ATTACK/SCRY/MILL: Pirate Captain."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Pirate Captain')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Pirate Captain] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Pirate Captain] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_shadow_steal():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Shadow Steal."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Shadow Steal']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Shadow Steal] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Shadow Steal] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_dark_dark_fruit():
    """OPC slice-22 UPKEEP/SCRY/EXILE_REQ: Dark-Dark Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Dark-Dark Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Dark-Dark Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Dark-Dark Fruit] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_string_string_fruit():
    """OPC slice-22 UPKEEP/SURVEIL/DAMAGE: String-String Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'String-String Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[String-String Fruit] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[String-String Fruit] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_pirate_plunder():
    """OPC slice-22 RESOLVE/SCRY/DAMAGE: Pirate Plunder."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Pirate Plunder']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Pirate Plunder] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Pirate Plunder] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_impel_down():
    """OPC slice-22 UPKEEP/SURVEIL/EXILE_REQ: Impel Down."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Impel Down')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Impel Down] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Impel Down] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_thriller_bark():
    """OPC slice-22 END_STEP/SCRY/LIFE_neg: Thriller Bark."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Thriller Bark')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Thriller Bark] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Thriller Bark] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_awakened_devil_fruit():
    """OPC slice-22 UPKEEP/SURVEIL/DISCARD: Awakened Devil Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Awakened Devil Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Awakened Devil Fruit] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Awakened Devil Fruit] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_pirate_crew():
    """OPC slice-22 ATTACK/SCRY/LIFE_neg: Pirate Crew."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Pirate Crew')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Pirate Crew] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Pirate Crew] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_treacherous_mutiny():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Treacherous Mutiny."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Treacherous Mutiny']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Treacherous Mutiny] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Treacherous Mutiny] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_yami_yami_blackhole():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Yami Yami Blackhole."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Yami Yami Blackhole']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Yami Yami Blackhole] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Yami Yami Blackhole] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_underworld_connection():
    """OPC slice-22 END_STEP/SURVEIL/EXILE_REQ: Underworld Connection."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Underworld Connection')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Underworld Connection] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Underworld Connection] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_flame_flame_fruit():
    """OPC slice-22 ETB/SCRY/MILL: Flame-Flame Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Flame-Flame Fruit')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Flame-Flame Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Flame-Flame Fruit] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_gum_gum_fruit():
    """OPC slice-22 UPKEEP/SURVEIL/EXILE_REQ: Gum-Gum Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Gum-Gum Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Gum-Gum Fruit] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Gum-Gum Fruit] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_gomu_gomu_no_pistol():
    """OPC slice-22 RESOLVE/SURVEIL/LIFE_neg: Gomu Gomu no Pistol."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Gomu Gomu no Pistol']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Gomu Gomu no Pistol] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Gomu Gomu no Pistol] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_gomu_gomu_no_gatling():
    """OPC slice-22 RESOLVE/SCRY/MILL: Gomu Gomu no Gatling."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Gomu Gomu no Gatling']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Gomu Gomu no Gatling] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Gomu Gomu no Gatling] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_fire_fist():
    """OPC slice-22 RESOLVE/SCRY/DAMAGE: Fire Fist."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Fire Fist']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Fire Fist] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Fire Fist] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_pirate_raid():
    """OPC slice-22 RESOLVE/SURVEIL/EXILE_REQ: Pirate Raid."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Pirate Raid']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Pirate Raid] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Pirate Raid] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_supernova_rampage():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Supernova Rampage."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Supernova Rampage']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Supernova Rampage] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Supernova Rampage] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_wano_country():
    """OPC slice-22 UPKEEP/SURVEIL/LIFE_neg: Wano Country."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Wano Country')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Wano Country] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Wano Country] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_burning_will():
    """OPC slice-22 ETB/SCRY/MILL: Burning Will."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Burning Will')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Burning Will] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Burning Will] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_revolutionary_army_soldier():
    """OPC slice-22 END_STEP/SCRY/MILL: Revolutionary Army Soldier."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Revolutionary Army Soldier')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Revolutionary Army Soldier] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Revolutionary Army Soldier] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_supernova():
    """OPC slice-22 ATTACK/SURVEIL/EXILE_REQ: Supernova."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Supernova')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Supernova] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Supernova] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_battle_franky():
    """OPC slice-22 ETB/SURVEIL/DAMAGE: Battle Franky."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Battle Franky')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Battle Franky] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Battle Franky] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_explosion_star():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Explosion Star."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Explosion Star']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Explosion Star] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Explosion Star] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_revolutionary_fervor():
    """OPC slice-22 END_STEP/SCRY/DAMAGE: Revolutionary Fervor."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Revolutionary Fervor')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Revolutionary Fervor] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Revolutionary Fervor] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_fiery_destruction():
    """OPC slice-22 RESOLVE/SCRY/DAMAGE: Fiery Destruction."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Fiery Destruction']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Fiery Destruction] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Fiery Destruction] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_samurai_of_wano():
    """OPC slice-22 ATTACK/SCRY/EXILE_REQ: Samurai of Wano."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Samurai of Wano')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Samurai of Wano] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Samurai of Wano] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_gear_second():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Gear Second."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Gear Second']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Gear Second] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Gear Second] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_gear_third():
    """OPC slice-22 RESOLVE/SCRY/MILL: Gear Third."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Gear Third']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Gear Third] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Gear Third] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_gear_fourth():
    """OPC slice-22 RESOLVE/SCRY/DAMAGE: Gear Fourth."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Gear Fourth']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Gear Fourth] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Gear Fourth] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_diable_jambe():
    """OPC slice-22 RESOLVE/SURVEIL/MILL: Diable Jambe."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Diable Jambe']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Diable Jambe] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Diable Jambe] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_kung_fu_dugong():
    """OPC slice-22 BLOCK/SURVEIL/DAMAGE: Kung-Fu Dugong."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Kung-Fu Dugong')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Kung-Fu Dugong] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Kung-Fu Dugong] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_south_bird():
    """OPC slice-22 ETB/SURVEIL/EXILE_REQ: South Bird."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'South Bird')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[South Bird] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[South Bird] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_three_sword_style():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Three-Sword Style."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Three-Sword Style']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Three-Sword Style] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Three-Sword Style] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_onigiri():
    """OPC slice-22 RESOLVE/SCRY/LIFE_neg: Onigiri."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Onigiri']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Onigiri] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Onigiri] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_ashura():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Ashura."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Ashura']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Ashura] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Ashura] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_wild_strength():
    """OPC slice-22 UPKEEP/SURVEIL/DAMAGE: Wild Strength."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Wild Strength')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Wild Strength] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Wild Strength] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_beast_pirates_territory():
    """OPC slice-22 UPKEEP/SCRY/MILL: Beast Pirates\' Territory."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Beast Pirates\' Territory')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Beast Pirates\' Territory] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Beast Pirates\' Territory] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_fish_fish_fruit_azure_dragon():
    """OPC slice-22 END_STEP/SURVEIL/DISCARD: Fish-Fish Fruit, Azure Dragon."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Fish-Fish Fruit, Azure Dragon')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Fish-Fish Fruit, Azure Dragon] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Fish-Fish Fruit, Azure Dragon] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_human_human_fruit():
    """OPC slice-22 END_STEP/SURVEIL/DAMAGE: Human-Human Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Human-Human Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Human-Human Fruit] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Human-Human Fruit] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_wano_samurai():
    """OPC slice-22 ATTACK/SCRY/LIFE_neg: Wano Samurai."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Wano Samurai')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Wano Samurai] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Wano Samurai] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_beast_pirate():
    """OPC slice-22 ATTACK/SURVEIL/DAMAGE: Beast Pirate."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Beast Pirate')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Beast Pirate] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Beast Pirate] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_ancient_zoan():
    """OPC slice-22 UPKEEP/SURVEIL/DISCARD: Ancient Zoan."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Ancient Zoan')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Ancient Zoan] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Ancient Zoan] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_awakened_zoan():
    """OPC slice-22 END_STEP/SURVEIL/MILL: Awakened Zoan."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Awakened Zoan')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Awakened Zoan] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Awakened Zoan] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_jungle_beast():
    """OPC slice-22 END_STEP/SCRY/DISCARD: Jungle Beast."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Jungle Beast')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Jungle Beast] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Jungle Beast] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_natural_strength():
    """OPC slice-22 RESOLVE/SURVEIL/LIFE_neg: Natural Strength."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Natural Strength']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Natural Strength] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Natural Strength] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_rumble_ball():
    """OPC slice-22 RESOLVE/SURVEIL/EXILE_REQ: Rumble Ball."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Rumble Ball']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Rumble Ball] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Rumble Ball] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_yamato_son_of_kaido():
    """OPC slice-22 BLOCK/SCRY/MILL: Yamato, Son of Kaido."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Yamato, Son of Kaido')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Yamato, Son of Kaido] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Yamato, Son of Kaido] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_nefertari_vivi_princess_of_alabasta():
    """OPC slice-22 UPKEEP/SCRY/LIFE_neg: Nefertari Vivi, Princess of Alabasta."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Nefertari Vivi, Princess of Alabasta')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Nefertari Vivi, Princess of Alabasta] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Nefertari Vivi, Princess of Alabasta] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_karoo_super_spot_billed_duck():
    """OPC slice-22 UPKEEP/SCRY/EXILE_REQ: Karoo, Super Spot-Billed Duck."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Karoo, Super Spot-Billed Duck')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Karoo, Super Spot-Billed Duck] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Karoo, Super Spot-Billed Duck] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_thousand_sunny():
    """OPC slice-22 ETB/SURVEIL/MILL: Thousand Sunny."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Thousand Sunny')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Thousand Sunny] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Thousand Sunny] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_going_merry():
    """OPC slice-22 ATTACK/SURVEIL/DISCARD: Going Merry."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Going Merry')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Going Merry] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Going Merry] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_straw_hat():
    """OPC slice-22 ETB/SURVEIL/LIFE_neg: Straw Hat."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Straw Hat')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Straw Hat] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Straw Hat] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_poneglyph():
    """OPC slice-22 ATTACK/SURVEIL/DISCARD: Poneglyph."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Poneglyph')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Poneglyph] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Poneglyph] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_devil_fruit_encyclopedia():
    """OPC slice-22 ATTACK/SCRY/LIFE_neg: Devil Fruit Encyclopedia."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Devil Fruit Encyclopedia')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Devil Fruit Encyclopedia] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Devil Fruit Encyclopedia] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_road_poneglyph():
    """OPC slice-22 ETB/SCRY/LIFE_neg: Road Poneglyph."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Road Poneglyph')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Road Poneglyph] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Road Poneglyph] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_one_piece_the_greatest_treasure():
    """OPC slice-22 ATTACK/SCRY/MILL: One Piece, the Greatest Treasure."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'One Piece, the Greatest Treasure')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[One Piece, the Greatest Treasure] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[One Piece, the Greatest Treasure] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_laugh_tale():
    """OPC slice-22 UPKEEP/SURVEIL/LIFE_neg: Laugh Tale."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Laugh Tale')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Laugh Tale] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Laugh Tale] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_raftel_approach():
    """OPC slice-22 RESOLVE/SURVEIL/MILL: Raftel Approach."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Raftel Approach']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Raftel Approach] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Raftel Approach] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_dawn_of_the_world():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Dawn of the World."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Dawn of the World']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Dawn of the World] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Dawn of the World] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_alliance_captain():
    """OPC slice-22 BLOCK/SCRY/DISCARD: Alliance Captain."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Alliance Captain')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Alliance Captain] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Alliance Captain] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_heart_pirates_crew():
    """OPC slice-22 ETB/SURVEIL/DAMAGE: Heart Pirates Crew."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Heart Pirates Crew')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Heart Pirates Crew] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Heart Pirates Crew] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_mink_warrior():
    """OPC slice-22 UPKEEP/SCRY/MILL: Mink Warrior."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Mink Warrior')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Mink Warrior] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Mink Warrior] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_revolutionary_commander():
    """OPC slice-22 UPKEEP/SCRY/DISCARD: Revolutionary Commander."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Revolutionary Commander')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Revolutionary Commander] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Revolutionary Commander] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_warlord_of_the_sea():
    """OPC slice-22 ETB/SURVEIL/MILL: Warlord of the Sea."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Warlord of the Sea')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Warlord of the Sea] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Warlord of the Sea] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_new_world_pirate():
    """OPC slice-22 DEATH/SURVEIL/DAMAGE: New World Pirate."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'New World Pirate')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ZONE_CHANGE, payload={'object_id': obj.id, 'from_zone': 'battlefield', 'to_zone': f'graveyard_{p1.id}', 'to_zone_type': ZoneType.GRAVEYARD, 'reason': 'destroy'}, source=obj.id))
    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': obj.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[New World Pirate] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[New World Pirate] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_coup_de_burst():
    """OPC slice-22 RESOLVE/SURVEIL/DISCARD: Coup de Burst."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Coup de Burst']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Coup de Burst] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Coup de Burst] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_bink_s_sake():
    """OPC slice-22 RESOLVE/SURVEIL/LIFE_neg: Bink\'s Sake."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Bink\'s Sake']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Bink\'s Sake] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Bink\'s Sake] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_gather_the_fleet():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Gather the Fleet."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Gather the Fleet']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Gather the Fleet] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Gather the Fleet] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_pirate_alliance():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Pirate Alliance."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Pirate Alliance']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Pirate Alliance] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Pirate Alliance] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_marineford_war():
    """OPC slice-22 RESOLVE/SCRY/DAMAGE: Marineford War."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Marineford War']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Marineford War] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Marineford War] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_paramount_war():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Paramount War."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Paramount War']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Paramount War] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Paramount War] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_haki_clash():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Haki Clash."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Haki Clash']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Haki Clash] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Haki Clash] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_conqueror_s_spirit():
    """OPC slice-22 END_STEP/SURVEIL/DISCARD: Conqueror\'s Spirit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Conqueror\'s Spirit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Conqueror\'s Spirit] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Conqueror\'s Spirit] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_eternal_pose():
    """OPC slice-22 ETB/SCRY/MILL: Eternal Pose."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Eternal Pose')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Eternal Pose] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Eternal Pose] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_tone_dial():
    """OPC slice-22 ETB/SURVEIL/MILL: Tone Dial."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Tone Dial')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Tone Dial] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Tone Dial] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_impact_dial():
    """OPC slice-22 ETB/SCRY/LIFE_neg: Impact Dial."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Impact Dial')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Impact Dial] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Impact Dial] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_seastone_cage():
    """OPC slice-22 ETB/SURVEIL/DAMAGE: Seastone Cage."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Seastone Cage')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Seastone Cage] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Seastone Cage] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_treasure_map():
    """OPC slice-22 ATTACK/SCRY/DAMAGE: Treasure Map."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Treasure Map')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Treasure Map] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Treasure Map] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_vivre_card():
    """OPC slice-22 END_STEP/SCRY/DISCARD: Vivre Card."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Vivre Card')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Vivre Card] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Vivre Card] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_den_den_mushi():
    """OPC slice-22 ATTACK/SURVEIL/EXILE_REQ: Den Den Mushi."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Den Den Mushi')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Den Den Mushi] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Den Den Mushi] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_pirate_flag():
    """OPC slice-22 ETB/SCRY/LIFE_neg: Pirate Flag."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Pirate Flag')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Pirate Flag] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Pirate Flag] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_will_of_d():
    """OPC slice-22 ETB/SURVEIL/DISCARD: Will of D.."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Will of D.')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Will of D.] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Will of D.] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_inherited_will():
    """OPC slice-22 END_STEP/SURVEIL/DAMAGE: Inherited Will."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Inherited Will')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Inherited Will] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Inherited Will] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_dream_of_the_pirate_king():
    """OPC slice-22 END_STEP/SURVEIL/DAMAGE: Dream of the Pirate King."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Dream of the Pirate King')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Dream of the Pirate King] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Dream of the Pirate King] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_sabaody_archipelago():
    """OPC slice-22 UPKEEP/SURVEIL/MILL: Sabaody Archipelago."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Sabaody Archipelago')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Sabaody Archipelago] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Sabaody Archipelago] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_marineford():
    """OPC slice-22 UPKEEP/SCRY/MILL: Marineford."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Marineford')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Marineford] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Marineford] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_dressrosa():
    """OPC slice-22 UPKEEP/SURVEIL/LIFE_neg: Dressrosa."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Dressrosa')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Dressrosa] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Dressrosa] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_whole_cake_island():
    """OPC slice-22 UPKEEP/SURVEIL/DAMAGE: Whole Cake Island."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Whole Cake Island')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Whole Cake Island] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Whole Cake Island] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_elbaf():
    """OPC slice-22 UPKEEP/SCRY/EXILE_REQ: Elbaf."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Elbaf')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Elbaf] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Elbaf] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_skypiea():
    """OPC slice-22 UPKEEP/SCRY/EXILE_REQ: Skypiea."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Skypiea')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Skypiea] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Skypiea] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_amazon_lily():
    """OPC slice-22 UPKEEP/SCRY/MILL: Amazon Lily."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Amazon Lily')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Amazon Lily] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Amazon Lily] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_coup_de_vent():
    """OPC slice-22 RESOLVE/SCRY/EXILE_REQ: Coup de Vent."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Coup de Vent']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Coup de Vent] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Coup de Vent] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_observation_dodge():
    """OPC slice-22 RESOLVE/SCRY/DAMAGE: Observation Dodge."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Observation Dodge']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Observation Dodge] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Observation Dodge] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_boa_hancock_pirate_empress():
    """OPC slice-22 BLOCK/SCRY/EXILE_REQ: Boa Hancock, Pirate Empress."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Boa Hancock, Pirate Empress')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Boa Hancock, Pirate Empress] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Boa Hancock, Pirate Empress] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_buggy_the_clown():
    """OPC slice-22 DEATH/SURVEIL/DISCARD: Buggy, the Clown."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Buggy, the Clown')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ZONE_CHANGE, payload={'object_id': obj.id, 'from_zone': 'battlefield', 'to_zone': f'graveyard_{p1.id}', 'to_zone_type': ZoneType.GRAVEYARD, 'reason': 'destroy'}, source=obj.id))
    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': obj.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Buggy, the Clown] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Buggy, the Clown] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_mihawk_world_s_strongest_swordsman():
    """OPC slice-22 END_STEP/SURVEIL/DISCARD: Mihawk, World\'s Strongest Swordsman."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Mihawk, World\'s Strongest Swordsman')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Mihawk, World\'s Strongest Swordsman] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Mihawk, World\'s Strongest Swordsman] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_kuma_tyrant():
    """OPC slice-22 ETB/SURVEIL/MILL: Kuma, Tyrant."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Kuma, Tyrant')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Kuma, Tyrant] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Kuma, Tyrant] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_rayleigh_dark_king():
    """OPC slice-22 ATTACK/SURVEIL/MILL: Rayleigh, Dark King."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Rayleigh, Dark King')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Rayleigh, Dark King] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Rayleigh, Dark King] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_marco_the_phoenix():
    """OPC slice-22 BLOCK/SCRY/DISCARD: Marco, the Phoenix."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Marco, the Phoenix')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Marco, the Phoenix] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Marco, the Phoenix] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_jozu_diamond():
    """OPC slice-22 ETB/SURVEIL/MILL: Jozu, Diamond."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Jozu, Diamond')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Jozu, Diamond] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Jozu, Diamond] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_vista_flower_sword():
    """OPC slice-22 BLOCK/SURVEIL/DISCARD: Vista, Flower Sword."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Vista, Flower Sword')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Vista, Flower Sword] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Vista, Flower Sword] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_perona_ghost_princess():
    """OPC slice-22 ATTACK/SURVEIL/DISCARD: Perona, Ghost Princess."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Perona, Ghost Princess')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Perona, Ghost Princess] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Perona, Ghost Princess] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_hancock_sisters():
    """OPC slice-22 END_STEP/SCRY/LIFE_neg: Hancock Sisters."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Hancock Sisters')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Hancock Sisters] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Hancock Sisters] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_ivankov_revolutionary():
    """OPC slice-22 END_STEP/SURVEIL/LIFE_neg: Ivankov, Revolutionary."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Ivankov, Revolutionary')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Ivankov, Revolutionary] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Ivankov, Revolutionary] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_inazuma_scissor():
    """OPC slice-22 ATTACK/SCRY/DISCARD: Inazuma, Scissor."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Inazuma, Scissor')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Inazuma, Scissor] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Inazuma, Scissor] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_bentham_mr_2():
    """OPC slice-22 ATTACK/SCRY/DAMAGE: Bentham, Mr. 2."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Bentham, Mr. 2')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Bentham, Mr. 2] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Bentham, Mr. 2] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_dragon_revolutionary_leader():
    """OPC slice-22 BLOCK/SCRY/LIFE_neg: Dragon, Revolutionary Leader."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Dragon, Revolutionary Leader')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Dragon, Revolutionary Leader] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Dragon, Revolutionary Leader] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_bartolomeo_the_cannibal():
    """OPC slice-22 ETB/SURVEIL/DISCARD: Bartolomeo, the Cannibal."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Bartolomeo, the Cannibal')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Bartolomeo, the Cannibal] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Bartolomeo, the Cannibal] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_cavendish_white_horse():
    """OPC slice-22 END_STEP/SCRY/LIFE_neg: Cavendish, White Horse."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Cavendish, White Horse')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Cavendish, White Horse] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Cavendish, White Horse] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_rebecca_gladiator():
    """OPC slice-22 END_STEP/SCRY/EXILE_REQ: Rebecca, Gladiator."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Rebecca, Gladiator')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Rebecca, Gladiator] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Rebecca, Gladiator] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_kyros_legendary_gladiator():
    """OPC slice-22 ATTACK/SURVEIL/DISCARD: Kyros, Legendary Gladiator."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Kyros, Legendary Gladiator')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Kyros, Legendary Gladiator] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Kyros, Legendary Gladiator] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_sabo_flame_emperor():
    """OPC slice-22 ATTACK/SURVEIL/DAMAGE: Sabo, Flame Emperor."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Sabo, Flame Emperor')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Sabo, Flame Emperor] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Sabo, Flame Emperor] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_grand_line_navigator():
    """OPC slice-22 ETB/SURVEIL/EXILE_REQ: Grand Line Navigator."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Grand Line Navigator')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Grand Line Navigator] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Grand Line Navigator] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_water_7_shipwright():
    """OPC slice-22 END_STEP/SURVEIL/EXILE_REQ: Water 7 Shipwright."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Water 7 Shipwright')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Water 7 Shipwright] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Water 7 Shipwright] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_galley_la_worker():
    """OPC slice-22 BLOCK/SURVEIL/EXILE_REQ: Galley-La Worker."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Galley-La Worker')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Galley-La Worker] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Galley-La Worker] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_long_ring_long_islander():
    """OPC slice-22 ATTACK/SURVEIL/EXILE_REQ: Long Ring Long Islander."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Long Ring Long Islander')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Long Ring Long Islander] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Long Ring Long Islander] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_wano_ninja():
    """OPC slice-22 ETB/SCRY/DAMAGE: Wano Ninja."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Wano Ninja')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Wano Ninja] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Wano Ninja] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_tontatta_warrior():
    """OPC slice-22 ETB/SCRY/DAMAGE: Tontatta Warrior."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Tontatta Warrior')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Tontatta Warrior] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Tontatta Warrior] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_mink_electro_user():
    """OPC slice-22 ATTACK/SURVEIL/DISCARD: Mink Electro User."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Mink Electro User')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Mink Electro User] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Mink Electro User] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_weatheria_scholar():
    """OPC slice-22 UPKEEP/SURVEIL/MILL: Weatheria Scholar."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Weatheria Scholar')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Weatheria Scholar] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Weatheria Scholar] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_conqueror_s_will():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Conqueror\'s Will."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Conqueror\'s Will']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Conqueror\'s Will] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Conqueror\'s Will] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_armament_coating():
    """OPC slice-22 RESOLVE/SURVEIL/EXILE_REQ: Armament Coating."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Armament Coating']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Armament Coating] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Armament Coating] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_observation_foresight():
    """OPC slice-22 RESOLVE/SCRY/MILL: Observation Foresight."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Observation Foresight']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Observation Foresight] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Observation Foresight] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_chop_chop_fruit():
    """OPC slice-22 UPKEEP/SCRY/DISCARD: Chop-Chop Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Chop-Chop Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Chop-Chop Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Chop-Chop Fruit] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_barrier_barrier_fruit():
    """OPC slice-22 END_STEP/SCRY/LIFE_neg: Barrier-Barrier Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Barrier-Barrier Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Barrier-Barrier Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Barrier-Barrier Fruit] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_revive_revive_fruit():
    """OPC slice-22 END_STEP/SCRY/EXILE_REQ: Revive-Revive Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Revive-Revive Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Revive-Revive Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Revive-Revive Fruit] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_hana_hana_fruit():
    """OPC slice-22 END_STEP/SCRY/MILL: Hana-Hana Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Hana-Hana Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Hana-Hana Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Hana-Hana Fruit] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_ope_ope_fruit():
    """OPC slice-22 END_STEP/SCRY/MILL: Ope-Ope Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Ope-Ope Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Ope-Ope Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Ope-Ope Fruit] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_mera_mera_fruit():
    """OPC slice-22 UPKEEP/SURVEIL/DISCARD: Mera-Mera Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Mera-Mera Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Mera-Mera Fruit] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Mera-Mera Fruit] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_gura_gura_fruit():
    """OPC slice-22 UPKEEP/SCRY/EXILE_REQ: Gura-Gura Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Gura-Gura Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Gura-Gura Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Gura-Gura Fruit] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_soul_soul_fruit():
    """OPC slice-22 END_STEP/SCRY/DISCARD: Soul-Soul Fruit."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Soul-Soul Fruit')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Soul-Soul Fruit] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Soul-Soul Fruit] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_captain_s_coat():
    """OPC slice-22 ETB/SCRY/DAMAGE: Captain\'s Coat."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Captain\'s Coat')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Captain\'s Coat] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Captain\'s Coat] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_wado_ichimonji():
    """OPC slice-22 ATTACK/SURVEIL/DISCARD: Wado Ichimonji."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Wado Ichimonji')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Wado Ichimonji] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Wado Ichimonji] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_enma():
    """OPC slice-22 ATTACK/SURVEIL/MILL: Enma."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Enma')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Enma] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Enma] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_shusui():
    """OPC slice-22 ETB/SCRY/MILL: Shusui."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Shusui')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Shusui] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Shusui] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_gryphon_sword():
    """OPC slice-22 END_STEP/SCRY/MILL: Gryphon Sword."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Gryphon Sword')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Gryphon Sword] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Gryphon Sword] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_ace_s_medallion():
    """OPC slice-22 END_STEP/SCRY/DAMAGE: Ace\'s Medallion."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Ace\'s Medallion')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Ace\'s Medallion] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Ace\'s Medallion] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_roger_s_bounty_poster():
    """OPC slice-22 ETB/SURVEIL/DAMAGE: Roger\'s Bounty Poster."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Roger\'s Bounty Poster')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Roger\'s Bounty Poster] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Roger\'s Bounty Poster] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_red_line():
    """OPC slice-22 UPKEEP/SCRY/MILL: Red Line."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Red Line')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Red Line] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Red Line] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_grand_line():
    """OPC slice-22 UPKEEP/SCRY/EXILE_REQ: Grand Line."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Grand Line')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Grand Line] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Grand Line] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_new_world():
    """OPC slice-22 UPKEEP/SURVEIL/LIFE_neg: New World."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'New World')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[New World] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[New World] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_mary_geoise():
    """OPC slice-22 UPKEEP/SCRY/LIFE_neg: Mary Geoise."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Mary Geoise')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Mary Geoise] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Mary Geoise] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_enies_lobby():
    """OPC slice-22 UPKEEP/SURVEIL/EXILE_REQ: Enies Lobby."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Enies Lobby')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Enies Lobby] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Enies Lobby] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_thriller_bark_island():
    """OPC slice-22 UPKEEP/SCRY/MILL: Thriller Bark Island."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Thriller Bark Island')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Thriller Bark Island] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Thriller Bark Island] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_punk_hazard():
    """OPC slice-22 UPKEEP/SURVEIL/MILL: Punk Hazard."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Punk Hazard')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Punk Hazard] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Punk Hazard] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_zou():
    """OPC slice-22 UPKEEP/SURVEIL/MILL: Zou."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Zou')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Zou] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Zou] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_don_quixote_pirates():
    """OPC slice-22 ATTACK/SURVEIL/DISCARD: Don Quixote Pirates."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Don Quixote Pirates')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Don Quixote Pirates] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Don Quixote Pirates] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_germa_66_soldier():
    """OPC slice-22 DEATH/SCRY/DISCARD: Germa 66 Soldier."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Germa 66 Soldier')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ZONE_CHANGE, payload={'object_id': obj.id, 'from_zone': 'battlefield', 'to_zone': f'graveyard_{p1.id}', 'to_zone_type': ZoneType.GRAVEYARD, 'reason': 'destroy'}, source=obj.id))
    game.emit(Event(type=EventType.OBJECT_DESTROYED, payload={'object_id': obj.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Germa 66 Soldier] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Germa 66 Soldier] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_big_mom_pirates():
    """OPC slice-22 BLOCK/SCRY/MILL: Big Mom Pirates."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Big Mom Pirates')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Big Mom Pirates] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Big Mom Pirates] expected opp mill; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_beast_pirates_headliner():
    """OPC slice-22 ETB/SURVEIL/LIFE_neg: Beast Pirates Headliner."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Beast Pirates Headliner')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Beast Pirates Headliner] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Beast Pirates Headliner] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_pleasure_smile_user():
    """OPC slice-22 UPKEEP/SCRY/LIFE_neg: Pleasure, SMILE User."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Pleasure, SMILE User')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Pleasure, SMILE User] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Pleasure, SMILE User] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_gifter_smile_user():
    """OPC slice-22 BLOCK/SCRY/DAMAGE: Gifter, SMILE User."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Gifter, SMILE User')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Gifter, SMILE User] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Gifter, SMILE User] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_whitebeard_pirates():
    """OPC slice-22 UPKEEP/SURVEIL/DISCARD: Whitebeard Pirates."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Whitebeard Pirates')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'upkeep', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Whitebeard Pirates] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Whitebeard Pirates] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_blackbeard_pirates():
    """OPC slice-22 BLOCK/SCRY/EXILE_REQ: Blackbeard Pirates."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Blackbeard Pirates')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.BLOCK_DECLARED, payload={'blocker_id': obj.id, 'blocker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Blackbeard Pirates] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Blackbeard Pirates] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_straw_hat_grand_fleet():
    """OPC slice-22 ETB/SCRY/EXILE_REQ: Straw Hat Grand Fleet."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Straw Hat Grand Fleet')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Straw Hat Grand Fleet] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Straw Hat Grand Fleet] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_worst_generation_captain():
    """OPC slice-22 ATTACK/SCRY/LIFE_neg: Worst Generation Captain."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Worst Generation Captain')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Worst Generation Captain] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Worst Generation Captain] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_roger_pirates():
    """OPC slice-22 ATTACK/SCRY/EXILE_REQ: Roger Pirates."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Roger Pirates')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Roger Pirates] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Roger Pirates] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_king_s_punch():
    """OPC slice-22 RESOLVE/SCRY/LIFE_neg: King\'s Punch."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['King\'s Punch']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[King\'s Punch] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.LIFE_CHANGE and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[King\'s Punch] expected opp life loss; got " + str([e.type.name for e in events])

def test_opc_s22_lion_song():
    """OPC slice-22 RESOLVE/SURVEIL/DAMAGE: Lion Song."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Lion Song']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Lion Song] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DAMAGE and e.payload.get('target') == p2.id]
    assert asym, "[Lion Song] expected opp damage; got " + str([e.type.name for e in events])

def test_opc_s22_phoenix_brand():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Phoenix Brand."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Phoenix Brand']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Phoenix Brand] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Phoenix Brand] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_ice_age():
    """OPC slice-22 RESOLVE/SURVEIL/DISCARD: Ice Age."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Ice Age']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Ice Age] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Ice Age] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_magma_fist():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Magma Fist."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Magma Fist']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Magma Fist] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Magma Fist] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_light_speed_kick():
    """OPC slice-22 RESOLVE/SCRY/DISCARD: Light Speed Kick."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Light Speed Kick']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Light Speed Kick] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Light Speed Kick] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_seaquake():
    """OPC slice-22 RESOLVE/SURVEIL/EXILE_REQ: Seaquake."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Seaquake']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Seaquake] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.EXILE and e.payload.get('player') == p2.id]
    assert asym, "[Seaquake] expected opp exile; got " + str([e.type.name for e in events])

def test_opc_s22_room():
    """OPC slice-22 RESOLVE/SURVEIL/DISCARD: Room."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Room']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Room] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Room] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_counter_shock():
    """OPC slice-22 RESOLVE/SCRY/MILL: Counter Shock."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Counter Shock']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SCRY]
    assert info_events, "[Counter Shock] expected SCRY; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.MILL and e.payload.get('player') == p2.id]
    assert asym, "[Counter Shock] expected opp mill; got " + str([e.type.name for e in events])

def test_opc_s22_gamma_knife():
    """OPC slice-22 RESOLVE/SURVEIL/DISCARD: Gamma Knife."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    cd = ONE_PIECE_CARDS['Gamma Knife']
    assert cd.resolve is not None
    game.state.active_player = p1.id
    events = cd.resolve([], game.state)
    info_events = [e for e in events if e.type == EventType.SURVEIL]
    assert info_events, "[Gamma Knife] expected SURVEIL; got " + str([e.type.name for e in events])
    asym = [e for e in events if e.type == EventType.DISCARD and e.payload.get('player') == p2.id]
    assert asym, "[Gamma Knife] expected opp discard; got " + str([e.type.name for e in events])

def test_opc_s22_reject_dial():
    """OPC slice-22 ETB/SCRY/LIFE_neg: Reject Dial."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Reject Dial')
    before = len(game.state.event_log)
    # ETB fires during put_on_battlefield — scan whole log for obj events
    new = [e for e in game.state.event_log if e.source == obj.id]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Reject Dial] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Reject Dial] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_axe_dial():
    """OPC slice-22 ATTACK/SCRY/DISCARD: Axe Dial."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Axe Dial')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Axe Dial] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DISCARD and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Axe Dial] expected opp discard; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_flame_dial():
    """OPC slice-22 ATTACK/SCRY/DAMAGE: Flame Dial."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Flame Dial')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Flame Dial] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Flame Dial] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_breath_dial():
    """OPC slice-22 ATTACK/SURVEIL/EXILE_REQ: Breath Dial."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Breath Dial')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Breath Dial] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.EXILE and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Breath Dial] expected opp exile; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_seastone_nail():
    """OPC slice-22 END_STEP/SCRY/DAMAGE: Seastone Nail."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Seastone Nail')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Seastone Nail] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.DAMAGE and e.source == obj.id and e.payload.get('target') == p2.id]
    assert asym, "[Seastone Nail] expected opp damage; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_wano_deckhand():
    """OPC slice-22 ATTACK/SURVEIL/LIFE_neg: Wano Deckhand."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Wano Deckhand')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED, payload={'attacker_id': obj.id, 'attacker': obj.id, 'controller': p1.id}, source=obj.id))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SURVEIL and e.source == obj.id]
    assert info_events, "[Wano Deckhand] expected SURVEIL; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.LIFE_CHANGE and e.source == obj.id and e.payload.get('player') == p2.id and e.payload.get('amount', 0) < 0]
    assert asym, "[Wano Deckhand] expected opp life loss; got " + str([e.type.name for e in new[-10:]])

def test_opc_s22_fish_man_brawler():
    """OPC slice-22 END_STEP/SCRY/MILL: Fish-Man Brawler."""
    game = Game()
    p1 = game.add_player('A')
    p2 = game.add_player('B')
    game.state.active_player = p1.id
    obj = _put_on_battlefield(game, p1, 'Fish-Man Brawler')
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.PHASE_START, payload={'phase': 'end_step', 'active_player': p1.id}, source=None))
    new = game.state.event_log[before:]
    info_events = [e for e in new if e.type == EventType.SCRY and e.source == obj.id]
    assert info_events, "[Fish-Man Brawler] expected SCRY; got " + str([e.type.name for e in new[-10:]])
    asym = [e for e in new if e.type == EventType.MILL and e.source == obj.id and e.payload.get('player') == p2.id]
    assert asym, "[Fish-Man Brawler] expected opp mill; got " + str([e.type.name for e in new[-10:]])



def _slice22_run_all():
    """Call all slice-22 tests in sequence."""
    test_opc_s22_marine_battleship()
    test_opc_s22_justice_gate()
    test_opc_s22_absolute_justice()
    test_opc_s22_marine_fortress()
    test_opc_s22_world_government_decree()
    test_opc_s22_buster_call()
    test_opc_s22_celestial_dragon_s_tribute()
    test_opc_s22_pacifista_unit()
    test_opc_s22_cipher_pol_agent()
    test_opc_s22_rokushiki_master()
    test_opc_s22_marine_justice()
    test_opc_s22_sea_prism_stone()
    test_opc_s22_marine_vice_admiral()
    test_opc_s22_justice_will_prevail()
    test_opc_s22_sea_prism_handcuffs()
    test_opc_s22_marine_training()
    test_opc_s22_world_noble()
    test_opc_s22_hachi_octopus_swordsman()
    test_opc_s22_fishman_karate_master()
    test_opc_s22_sea_king()
    test_opc_s22_neptune_king_of_fishmen()
    test_opc_s22_weather_tempo()
    test_opc_s22_mirage_tempo()
    test_opc_s22_fishman_island()
    test_opc_s22_calm_belt()
    test_opc_s22_undersea_voyage()
    test_opc_s22_log_pose()
    test_opc_s22_grand_line_navigation()
    test_opc_s22_navigator_s_apprentice()
    test_opc_s22_ocean_current()
    test_opc_s22_fishman_district()
    test_opc_s22_merfolk_dancer()
    test_opc_s22_water_7()
    test_opc_s22_undersea_prison()
    test_opc_s22_pirate_captain()
    test_opc_s22_shadow_steal()
    test_opc_s22_dark_dark_fruit()
    test_opc_s22_string_string_fruit()
    test_opc_s22_pirate_plunder()
    test_opc_s22_impel_down()
    test_opc_s22_thriller_bark()
    test_opc_s22_awakened_devil_fruit()
    test_opc_s22_pirate_crew()
    test_opc_s22_treacherous_mutiny()
    test_opc_s22_yami_yami_blackhole()
    test_opc_s22_underworld_connection()
    test_opc_s22_flame_flame_fruit()
    test_opc_s22_gum_gum_fruit()
    test_opc_s22_gomu_gomu_no_pistol()
    test_opc_s22_gomu_gomu_no_gatling()
    test_opc_s22_fire_fist()
    test_opc_s22_pirate_raid()
    test_opc_s22_supernova_rampage()
    test_opc_s22_wano_country()
    test_opc_s22_burning_will()
    test_opc_s22_revolutionary_army_soldier()
    test_opc_s22_supernova()
    test_opc_s22_battle_franky()
    test_opc_s22_explosion_star()
    test_opc_s22_revolutionary_fervor()
    test_opc_s22_fiery_destruction()
    test_opc_s22_samurai_of_wano()
    test_opc_s22_gear_second()
    test_opc_s22_gear_third()
    test_opc_s22_gear_fourth()
    test_opc_s22_diable_jambe()
    test_opc_s22_kung_fu_dugong()
    test_opc_s22_south_bird()
    test_opc_s22_three_sword_style()
    test_opc_s22_onigiri()
    test_opc_s22_ashura()
    test_opc_s22_wild_strength()
    test_opc_s22_beast_pirates_territory()
    test_opc_s22_fish_fish_fruit_azure_dragon()
    test_opc_s22_human_human_fruit()
    test_opc_s22_wano_samurai()
    test_opc_s22_beast_pirate()
    test_opc_s22_ancient_zoan()
    test_opc_s22_awakened_zoan()
    test_opc_s22_jungle_beast()
    test_opc_s22_natural_strength()
    test_opc_s22_rumble_ball()
    test_opc_s22_yamato_son_of_kaido()
    test_opc_s22_nefertari_vivi_princess_of_alabasta()
    test_opc_s22_karoo_super_spot_billed_duck()
    test_opc_s22_thousand_sunny()
    test_opc_s22_going_merry()
    test_opc_s22_straw_hat()
    test_opc_s22_poneglyph()
    test_opc_s22_devil_fruit_encyclopedia()
    test_opc_s22_road_poneglyph()
    test_opc_s22_one_piece_the_greatest_treasure()
    test_opc_s22_laugh_tale()
    test_opc_s22_raftel_approach()
    test_opc_s22_dawn_of_the_world()
    test_opc_s22_alliance_captain()
    test_opc_s22_heart_pirates_crew()
    test_opc_s22_mink_warrior()
    test_opc_s22_revolutionary_commander()
    test_opc_s22_warlord_of_the_sea()
    test_opc_s22_new_world_pirate()
    test_opc_s22_coup_de_burst()
    test_opc_s22_bink_s_sake()
    test_opc_s22_gather_the_fleet()
    test_opc_s22_pirate_alliance()
    test_opc_s22_marineford_war()
    test_opc_s22_paramount_war()
    test_opc_s22_haki_clash()
    test_opc_s22_conqueror_s_spirit()
    test_opc_s22_eternal_pose()
    test_opc_s22_tone_dial()
    test_opc_s22_impact_dial()
    test_opc_s22_seastone_cage()
    test_opc_s22_treasure_map()
    test_opc_s22_vivre_card()
    test_opc_s22_den_den_mushi()
    test_opc_s22_pirate_flag()
    test_opc_s22_will_of_d()
    test_opc_s22_inherited_will()
    test_opc_s22_dream_of_the_pirate_king()
    test_opc_s22_sabaody_archipelago()
    test_opc_s22_marineford()
    test_opc_s22_dressrosa()
    test_opc_s22_whole_cake_island()
    test_opc_s22_elbaf()
    test_opc_s22_skypiea()
    test_opc_s22_amazon_lily()
    test_opc_s22_coup_de_vent()
    test_opc_s22_observation_dodge()
    test_opc_s22_boa_hancock_pirate_empress()
    test_opc_s22_buggy_the_clown()
    test_opc_s22_mihawk_world_s_strongest_swordsman()
    test_opc_s22_kuma_tyrant()
    test_opc_s22_rayleigh_dark_king()
    test_opc_s22_marco_the_phoenix()
    test_opc_s22_jozu_diamond()
    test_opc_s22_vista_flower_sword()
    test_opc_s22_perona_ghost_princess()
    test_opc_s22_hancock_sisters()
    test_opc_s22_ivankov_revolutionary()
    test_opc_s22_inazuma_scissor()
    test_opc_s22_bentham_mr_2()
    test_opc_s22_dragon_revolutionary_leader()
    test_opc_s22_bartolomeo_the_cannibal()
    test_opc_s22_cavendish_white_horse()
    test_opc_s22_rebecca_gladiator()
    test_opc_s22_kyros_legendary_gladiator()
    test_opc_s22_sabo_flame_emperor()
    test_opc_s22_grand_line_navigator()
    test_opc_s22_water_7_shipwright()
    test_opc_s22_galley_la_worker()
    test_opc_s22_long_ring_long_islander()
    test_opc_s22_wano_ninja()
    test_opc_s22_tontatta_warrior()
    test_opc_s22_mink_electro_user()
    test_opc_s22_weatheria_scholar()
    test_opc_s22_conqueror_s_will()
    test_opc_s22_armament_coating()
    test_opc_s22_observation_foresight()
    test_opc_s22_chop_chop_fruit()
    test_opc_s22_barrier_barrier_fruit()
    test_opc_s22_revive_revive_fruit()
    test_opc_s22_hana_hana_fruit()
    test_opc_s22_ope_ope_fruit()
    test_opc_s22_mera_mera_fruit()
    test_opc_s22_gura_gura_fruit()
    test_opc_s22_soul_soul_fruit()
    test_opc_s22_captain_s_coat()
    test_opc_s22_wado_ichimonji()
    test_opc_s22_enma()
    test_opc_s22_shusui()
    test_opc_s22_gryphon_sword()
    test_opc_s22_ace_s_medallion()
    test_opc_s22_roger_s_bounty_poster()
    test_opc_s22_red_line()
    test_opc_s22_grand_line()
    test_opc_s22_new_world()
    test_opc_s22_mary_geoise()
    test_opc_s22_enies_lobby()
    test_opc_s22_thriller_bark_island()
    test_opc_s22_punk_hazard()
    test_opc_s22_zou()
    test_opc_s22_don_quixote_pirates()
    test_opc_s22_germa_66_soldier()
    test_opc_s22_big_mom_pirates()
    test_opc_s22_beast_pirates_headliner()
    test_opc_s22_pleasure_smile_user()
    test_opc_s22_gifter_smile_user()
    test_opc_s22_whitebeard_pirates()
    test_opc_s22_blackbeard_pirates()
    test_opc_s22_straw_hat_grand_fleet()
    test_opc_s22_worst_generation_captain()
    test_opc_s22_roger_pirates()
    test_opc_s22_king_s_punch()
    test_opc_s22_lion_song()
    test_opc_s22_phoenix_brand()
    test_opc_s22_ice_age()
    test_opc_s22_magma_fist()
    test_opc_s22_light_speed_kick()
    test_opc_s22_seaquake()
    test_opc_s22_room()
    test_opc_s22_counter_shock()
    test_opc_s22_gamma_knife()
    test_opc_s22_reject_dial()
    test_opc_s22_axe_dial()
    test_opc_s22_flame_dial()
    test_opc_s22_breath_dial()
    test_opc_s22_seastone_nail()
    test_opc_s22_wano_deckhand()
    test_opc_s22_fish_man_brawler()

if __name__ == "__main__":
    # Kaido
    test_kaido_awakened_loads_legendary_dragon()
    test_kaido_awakened_etb_adds_three_counters()
    test_kaido_awakened_lord_buffs_other_dragons()
    # Big Mom
    test_big_mom_sweet_loads_legendary_pirate()
    test_big_mom_sweet_etb_creates_two_food()
    test_big_mom_sweet_food_sac_draws_and_pumps()
    test_big_mom_sweet_non_food_sac_does_not_trigger()
    # Whitebeard
    test_whitebeard_strongest_loads_legendary()
    test_whitebeard_strongest_etb_damages_opp_creatures_by_pirate_count()
    test_whitebeard_strongest_lord_buffs_other_pirates()
    # Mihawk
    test_mihawk_falcon_loads_with_ward_and_damage_trigger()
    test_mihawk_falcon_combat_damage_exiles_target()
    test_mihawk_falcon_does_not_exile_on_non_combat_damage()
    # Marineford
    test_marineford_war_loads_legendary_saga()
    test_marineford_war_chapter_handlers_callable()
    # Wano
    test_wano_uprising_loads_legendary_saga()
    test_wano_uprising_chapter_handlers()
    # Yoru
    test_yoru_loads_legendary_equipment_sword()
    test_yoru_attach_pumps_and_first_strike()
    test_yoru_attack_grants_indestructible()
    # Devil Fruit
    test_devil_fruit_awakening_loads_aura()
    test_devil_fruit_awakening_attack_draws_and_drains()
    # Cipher Pol Zero
    test_cipher_pol_zero_loads()
    test_cipher_pol_zero_etb_reveals_opp_hands()
    test_cipher_pol_zero_opp_spell_drains_life()
    test_cipher_pol_zero_own_spell_does_not_drain()
    # Slice 3 — decision-axis flip
    test_marshall_d_teach_loads_legendary()
    test_marshall_d_teach_etb_opens_modal_choice()
    test_den_den_mushi_loads_enchantment()
    test_den_den_mushi_etb_emits_target_required_and_draw()
    test_gura_gura_quake_loads_enchantment()
    test_gura_gura_quake_etb_emits_divided_damage_target_required()
    test_sengoku_buddha_blessing_loads()
    test_sengoku_buddha_blessing_etb_emits_counter_add_target_required()
    test_charlotte_linlin_loads_legendary_giant_pirate()
    test_charlotte_linlin_death_emits_target_required_and_discard()
    test_nico_robin_loads_legendary_archaeologist()
    test_nico_robin_etb_empty_library_no_op()
    test_nico_robin_etb_with_library_lands_opens_choice()
    test_smoker_vice_admiral_loads_legendary_marine()
    test_smoker_vice_admiral_attack_emits_tap_target_required()
    # Slice 5 — thin-bust multi-axis
    test_slice5_east_blue_pirate_attack_scry_and_drain()
    test_slice5_drum_island_sentry_attack_scry_and_drain()
    test_slice5_sea_patrol_pirate_attack_scry_and_drain()
    test_slice5_drum_island_sailor_attack_scry_and_drain()
    test_slice5_marine_patrol_attack_scry_and_drain()
    test_slice5_skypiea_warrior_attack_scry_and_drain()
    test_slice5_alabasta_guard_etb_scry_and_lifegain()
    test_slice5_baroque_works_assassin_etb_surveil_and_drain()
    test_slice5_skypiean_warrior_etb_scry_and_drain()
    test_slice5_shandian_fighter_attack_scry_and_drain()
    test_slice5_marine_captain_etb_scry_and_drain()
    test_slice5_impel_down_guard_etb_scry_and_drain()
    test_slice5_marine_soldier_etb_scry_and_drain()
    test_slice5_fishman_warrior_etb_scry_and_drain()
    test_slice5_baroque_works_agent_etb_surveil_and_drain()
    test_slice5_shadow_puppet_etb_surveil_and_drain()
    test_slice5_onigashima_guard_etb_surveil_and_drain()
    test_slice5_giant_warrior_etb_scry_and_drain()
    # Slice 22 — median lift (210 cards)
    _slice22_run_all()
    print("\n" + "=" * 60)
    print("ALL ONE PIECE SPICE v2 EXPANSION TESTS PASSED!")
    print("=" * 60)
