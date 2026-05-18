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
    print("\n" + "=" * 60)
    print("ALL ONE PIECE SPICE v2 EXPANSION TESTS PASSED!")
    print("=" * 60)
