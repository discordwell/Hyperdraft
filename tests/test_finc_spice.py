"""
Final Fantasy Custom (FINC) Spice Pass Tests (Phase A1)

Validates the format-defining cards added/rewired for the Princess Catholicon
custom set (the renamed FF set, registry ``FINAL_FANTASY_CUSTOM_CARDS``).
Phase A1 — within current engine, no new helpers.

Cards covered:
- Sephiroth, Avatar of the Calamity (NEW — Limit Break build-around mythic)
- Cecil Harvey, Paladin of Mysidia (NEW — Limit Break self-sustain mythic)
- Crystals of Light (NEW — Saga uses make_saga_setup)
- Buster Sword (REWIRE — make_equipment_setup +3/+0 first strike, grants SOLDIER)
- Berserker (REWIRE — +2/+0 self pump on attack)
- Dragoon (REWIRE — self flying + ETB fight)
- Monk (REWIRE — +3/+3 EOT when attacks alone via make_attacks_alone_trigger)
- Limit Charge (REWIRE — life-loss adds charge counter; activated cash-in)

Mirrors the shape of `tests/test_zelda_spice.py` (ZLD A1 pilot).
"""

import os
import sys

# Resolve to this worktree's project root, not the parent checkout. Tests run
# from the worktree where the spice pass code lives — hard-coding
# '/Users/discordwell/Projects/HYPERDRAFT' (as the ZLD test template did)
# would load the parent's princess_catholicon.py instead of ours.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    get_power, get_toughness,
)
from src.engine.queries import has_ability
from src.cards.custom.princess_catholicon import FINAL_FANTASY_CUSTOM_CARDS


def _put_on_battlefield(game, player, card_name):
    """Mirror the Star Wars / ZLD spice test harness shape.

    create_object runs setup_interceptors for BATTLEFIELD/COMMAND zones.
    Putting the card in HAND first with ``card_def=None``, then emitting a
    ZONE_CHANGE into the battlefield, runs setup exactly once via the
    pipeline (the correct path)."""
    card_def = FINAL_FANTASY_CUSTOM_CARDS[card_name]
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
# Sephiroth, Avatar of the Calamity
# ============================================================================

def test_sephiroth_avatar_loads():
    """Setup registers self-flying + LB keyword grant + attack-drain."""
    print("\n=== Sephiroth Avatar: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    seph = _put_on_battlefield(game, p1, "Sephiroth, Avatar of the Calamity")
    assert seph.zone == ZoneType.BATTLEFIELD
    # Expect: flying (always), lb keyword grant, attack drain, plus the
    # static_pt_boost from make_limit_break (marker, +0/+0).
    assert len(seph.interceptor_ids) >= 3, (
        f"Expected ≥3 interceptors; got {len(seph.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(seph.interceptor_ids)}")


def test_sephiroth_avatar_flying_always():
    """Self-flying is unconditional — gotcha #1: must wire via make_keyword_grant."""
    print("\n=== Sephiroth Avatar: flying always ===")
    game = Game()
    p1 = game.add_player("Alice")
    seph = _put_on_battlefield(game, p1, "Sephiroth, Avatar of the Calamity")
    # Alice at default 20 life; LB not active. Flying still on.
    assert has_ability(seph, "flying", game.state), "Expected flying always"
    # double_strike / indestructible should NOT be on at 20 life.
    assert not has_ability(seph, "double_strike", game.state)
    assert not has_ability(seph, "indestructible", game.state)


def test_sephiroth_avatar_limit_break_grants_haste_double_strike_indestructible():
    """At life <=10, the LB keyword grant fires haste+double_strike+indestructible."""
    print("\n=== Sephiroth Avatar: LB grants ===")
    game = Game()
    p1 = game.add_player("Alice")
    seph = _put_on_battlefield(game, p1, "Sephiroth, Avatar of the Calamity")
    p1.life = 10
    assert has_ability(seph, "haste", game.state), "Expected haste at LB10"
    assert has_ability(seph, "double_strike", game.state), "Expected double_strike at LB10"
    assert has_ability(seph, "indestructible", game.state), "Expected indestructible at LB10"
    print(f"  Sephiroth at 10 life: haste/double_strike/indestructible all on")


def test_sephiroth_avatar_attack_drains_each_opponent():
    """Whenever Sephiroth attacks, each opponent loses 2 life."""
    print("\n=== Sephiroth Avatar: attack -> opp drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    seph = _put_on_battlefield(game, p1, "Sephiroth, Avatar of the Calamity")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': seph.id, 'attacker': seph.id, 'controller': p1.id},
        source=seph.id,
    ))
    after = game.state.event_log[before:]
    drains = [
        e for e in after
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -2
    ]
    assert drains, f"Expected -2 LIFE_CHANGE to opp; recent={_emitted_types(game)[-10:]}"
    print(f"  Drain events on attack: {len(drains)}")


# ============================================================================
# Cecil Harvey, Paladin of Mysidia
# ============================================================================

def test_cecil_harvey_loads():
    """Setup registers lifelink/vigilance grant + end-step LB drain."""
    print("\n=== Cecil Harvey: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cecil = _put_on_battlefield(game, p1, "Cecil Harvey, Paladin of Mysidia")
    assert cecil.zone == ZoneType.BATTLEFIELD
    assert has_ability(cecil, "lifelink", game.state)
    assert has_ability(cecil, "vigilance", game.state)
    assert len(cecil.interceptor_ids) >= 2


def test_cecil_harvey_end_step_drains_at_lb10():
    """At <=10 life, end step fires the drain/gain combo."""
    print("\n=== Cecil Harvey: end step drain at LB10 ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Cecil Harvey, Paladin of Mysidia")
    p1.life = 8

    # End step trigger filters on state.active_player (gotcha #8).
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    after = game.state.event_log[before:]

    opp_drains = [
        e for e in after
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -3
    ]
    own_gains = [
        e for e in after
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 3
    ]
    assert opp_drains, f"Expected -3 LIFE_CHANGE to opp; recent={_emitted_types(game)[-10:]}"
    assert own_gains, "Expected +3 LIFE_CHANGE to self"
    print(f"  Drains: {len(opp_drains)}, Gains: {len(own_gains)}")


def test_cecil_harvey_end_step_no_fire_above_lb10():
    """At 11+ life, the end step trigger is gated and emits nothing."""
    print("\n=== Cecil Harvey: end step no fire above LB10 ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p1, "Cecil Harvey, Paladin of Mysidia")
    p1.life = 20

    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': p1.id},
    ))
    after = game.state.event_log[before:]
    drains = [
        e for e in after
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -3
    ]
    assert not drains, f"LB should be inactive at 20 life; saw {len(drains)} drains"


# ============================================================================
# Crystals of Light (Saga)
# ============================================================================

def test_crystals_of_light_loads():
    """Saga subtype + interceptors registered, chapter I fires on ETB."""
    print("\n=== Crystals of Light: load + chapter I ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Crystals of Light")
    assert saga.zone == ZoneType.BATTLEFIELD
    assert "Saga" in saga.characteristics.subtypes
    # Saga ETB emits SAGA_LORE_ADDED + chapter I fires the scry placeholder.
    scrys = [
        e for e in game.state.event_log
        if e.type == EventType.ACTIVATE and e.payload.get('action') == 'scry'
    ]
    assert scrys, f"Expected chapter I scry placeholder; recent={_emitted_types(game)[-10:]}"
    assert scrys[-1].payload.get('amount') == 2


def test_crystals_of_light_chapter_ii_draws_card():
    """Advance to chapter II via PHASE_START draw, assert DRAW event."""
    print("\n=== Crystals of Light: chapter II draws ===")
    game = Game()
    p1 = game.add_player("Alice")
    saga = _put_on_battlefield(game, p1, "Crystals of Light")
    # Saga's etb_filter checks state.active_player == controller for the
    # draw-step trigger (canonical lore counter pattern).
    game.state.active_player = p1.id
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'draw', 'active_player': p1.id},
    ))
    after = game.state.event_log[before:]
    draws = [
        e for e in after
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert draws, f"Expected chapter II DRAW after PHASE_START draw; recent={_emitted_types(game)[-10:]}"
    print(f"  DRAW events after chapter II tick: {len(draws)}")


# ============================================================================
# Buster Sword
# ============================================================================

def test_buster_sword_loads():
    """make_equipment_setup registers PT-mod + first-strike + subtype grant + equip cost."""
    print("\n=== Buster Sword: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    sword = _put_on_battlefield(game, p1, "Buster Sword")
    assert sword.zone == ZoneType.BATTLEFIELD
    assert "Equipment" in sword.characteristics.subtypes
    activated = getattr(sword.state, 'activated_abilities', None)
    assert activated, "Expected an equip activated ability on Buster Sword"
    # Expect ≥3 interceptors: PT-mod, keyword grant, subtypes listener.
    assert len(sword.interceptor_ids) >= 3, (
        f"Expected ≥3 interceptors; got {len(sword.interceptor_ids)}"
    )


def test_buster_sword_pt_mod_on_attach():
    """ATTACH triggers +3/+0 on equipped creature via PT query aggregation."""
    print("\n=== Buster Sword: +3/+0 on attach ===")
    game = Game()
    p1 = game.add_player("Alice")
    sword = _put_on_battlefield(game, p1, "Buster Sword")
    knight = _put_on_battlefield(game, p1, "Holy Knight")
    base_p = get_power(knight, game.state)
    base_t = get_toughness(knight, game.state)

    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': sword.id, 'target_id': knight.id},
        source=sword.id,
    ))

    new_p = get_power(knight, game.state)
    new_t = get_toughness(knight, game.state)
    assert new_p == base_p + 3, f"Expected power +3: {base_p}->{new_p}"
    assert new_t == base_t, f"Expected toughness unchanged: {base_t}->{new_t}"
    assert has_ability(knight, "first_strike", game.state), "Expected first_strike on equipped"
    # Gotcha #13 / Phase 3 equipment: subtypes_to_add applies on ATTACH.
    assert "SOLDIER" in knight.characteristics.subtypes, (
        "Expected SOLDIER subtype to be added by Buster Sword on attach"
    )
    print(f"  Holy Knight: {base_p}/{base_t} -> {new_p}/{new_t} + first_strike + SOLDIER")


# ============================================================================
# Berserker
# ============================================================================

def test_berserker_loads():
    """Was empty stub; now registers an attack-trigger interceptor."""
    print("\n=== Berserker: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bk = _put_on_battlefield(game, p1, "Berserker")
    assert bk.zone == ZoneType.BATTLEFIELD
    assert bk.interceptor_ids, "Berserker should register at least one interceptor"


def test_berserker_attack_pumps_self():
    """Berserker attack emits PT_MODIFICATION +2/+0 EOT on itself."""
    print("\n=== Berserker: attack -> +2/+0 self ===")
    game = Game()
    p1 = game.add_player("Alice")
    bk = _put_on_battlefield(game, p1, "Berserker")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': bk.id, 'attacker': bk.id, 'controller': p1.id},
        source=bk.id,
    ))
    after = game.state.event_log[before:]
    pumps = [
        e for e in after
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == bk.id
        and e.payload.get('power_mod') == 2
        and e.payload.get('toughness_mod') == 0
        and e.payload.get('duration') == 'end_of_turn'
    ]
    assert pumps, f"Expected +2/+0 EOT PT_MOD; recent={_emitted_types(game)[-10:]}"
    print(f"  Self-pump events: {len(pumps)}")


# ============================================================================
# Dragoon
# ============================================================================

def test_dragoon_loads_with_flying():
    """Was empty stub; now grants self flying + ETB fight."""
    print("\n=== Dragoon: load + flying ===")
    game = Game()
    p1 = game.add_player("Alice")
    drg = _put_on_battlefield(game, p1, "Dragoon")
    assert drg.zone == ZoneType.BATTLEFIELD
    assert has_ability(drg, "flying", game.state), "Expected self-flying on Dragoon"


def test_dragoon_etb_emits_fight():
    """Dragoon's ETB emits a fight DAMAGE event."""
    print("\n=== Dragoon: ETB fight emit ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Snapshot before ETB so we can isolate the ETB events.
    drg = _put_on_battlefield(game, p1, "Dragoon")
    fights = [
        e for e in game.state.event_log
        if e.type == EventType.DAMAGE
        and e.payload.get('fight') is True
        and e.payload.get('source') == drg.id
    ]
    assert fights, f"Expected fight DAMAGE event on ETB; recent={_emitted_types(game)[-10:]}"
    print(f"  Fight emits: {len(fights)}")


# ============================================================================
# Monk
# ============================================================================

def test_monk_loads():
    print("\n=== Monk: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    mk = _put_on_battlefield(game, p1, "Monk")
    assert mk.zone == ZoneType.BATTLEFIELD
    assert mk.interceptor_ids, "Monk should register an attacks-alone trigger"


def test_monk_alone_attack_pumps_self():
    """COMBAT_DECLARED with attackers=[monk] fires +3/+3 EOT on Monk."""
    print("\n=== Monk: attacks alone -> +3/+3 ===")
    game = Game()
    p1 = game.add_player("Alice")
    mk = _put_on_battlefield(game, p1, "Monk")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': p1.id, 'attackers': [mk.id]},
    ))
    after = game.state.event_log[before:]
    pumps = [
        e for e in after
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == mk.id
        and e.payload.get('power_mod') == 3
        and e.payload.get('toughness_mod') == 3
        and e.payload.get('duration') == 'end_of_turn'
    ]
    assert pumps, f"Expected +3/+3 EOT pump; recent={_emitted_types(game)[-10:]}"


def test_monk_attacks_with_buddy_does_not_pump():
    """Monk attacking with another attacker should NOT fire the alone trigger."""
    print("\n=== Monk: not alone -> no pump ===")
    game = Game()
    p1 = game.add_player("Alice")
    mk = _put_on_battlefield(game, p1, "Monk")
    samurai = _put_on_battlefield(game, p1, "Samurai")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': p1.id, 'attackers': [mk.id, samurai.id]},
    ))
    after = game.state.event_log[before:]
    pumps = [
        e for e in after
        if e.type == EventType.PT_MODIFICATION
        and e.payload.get('object_id') == mk.id
    ]
    assert not pumps, f"Monk should not pump when not alone; saw {len(pumps)} pumps"


# ============================================================================
# Limit Charge
# ============================================================================

def test_limit_charge_loads():
    """Was unwired enchantment; now has life-loss trigger + counter tracker + activated."""
    print("\n=== Limit Charge: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    lc = _put_on_battlefield(game, p1, "Limit Charge")
    assert lc.zone == ZoneType.BATTLEFIELD
    activated = getattr(lc.state, 'activated_abilities', None)
    assert activated, "Expected an activated ability on Limit Charge"
    assert len(lc.interceptor_ids) >= 2, (
        f"Expected ≥2 interceptors (life-loss + counter tracker); got {len(lc.interceptor_ids)}"
    )


def test_limit_charge_own_life_loss_adds_counter():
    """Own controller losing life emits a COUNTER_ADDED with counter_type='charge'."""
    print("\n=== Limit Charge: own life loss -> charge ===")
    game = Game()
    p1 = game.add_player("Alice")
    lc = _put_on_battlefield(game, p1, "Limit Charge")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p1.id, 'amount': -2},
        source=lc.id,
    ))
    after = game.state.event_log[before:]
    charges = [
        e for e in after
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == lc.id
        and e.payload.get('counter_type') == 'charge'
    ]
    assert charges, f"Expected charge COUNTER_ADDED; recent={_emitted_types(game)[-10:]}"
    # Counter tracker should have written charge total to obj.state.
    assert getattr(lc.state, '_charge_counters', 0) >= 1, (
        f"Expected _charge_counters >=1; got {getattr(lc.state, '_charge_counters', 0)}"
    )
    print(f"  Charge counters: {getattr(lc.state, '_charge_counters', 0)}")


def test_limit_charge_opp_life_loss_does_not_add_counter():
    """Opponent life loss does NOT charge Limit Charge."""
    print("\n=== Limit Charge: opp life loss -> no charge ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    lc = _put_on_battlefield(game, p1, "Limit Charge")

    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': p2.id, 'amount': -3},
        source=lc.id,
    ))
    after = game.state.event_log[before:]
    charges = [
        e for e in after
        if e.type == EventType.COUNTER_ADDED
        and e.payload.get('object_id') == lc.id
    ]
    assert not charges, "Opp life loss should not charge Limit Charge"


# ============================================================================
# Slice 5 thin-bust — 26 vanilla cards lifted to multi-axis depth
# ============================================================================
#
# Each test follows the same shape used by DBZ slice-4: put the card on the
# battlefield, fire the appropriate trigger (ETB or ATTACK_DECLARED), and
# assert at least one SCRY/SURVEIL emission + the asymmetry/synergy event the
# buff promises. Tests are intentionally light — coverage, not balance.


def _events_after(game, before, kind, **payload_match):
    """Helper: filter events newer than ``before`` matching ``kind`` and the
    given payload key/values. ``before`` is the event-log length snapshot."""
    out = []
    for e in game.state.event_log[before:]:
        if e.type != kind:
            continue
        if all(e.payload.get(k) == v for k, v in payload_match.items()):
            out.append(e)
    return out


def test_cadet_mage_etb_scrys_and_drains_each_opp_when_opp_has_creature():
    print("\n=== Cadet Mage: ETB scry + opp drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    # Put an opp creature down first so the threat gate fires.
    _put_on_battlefield(game, p2, "Goblin")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Cadet Mage")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys, "Expected scry 1 on Cadet Mage ETB"
    assert drains, "Expected -1 life to opp on Cadet Mage ETB"


def test_junior_summoner_etb_scrys_more_with_another_summoner():
    print("\n=== Junior Summoner: ETB scry escalates ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    # Drop a second Summoner first; same controller.
    _put_on_battlefield(game, p1, "Evoker")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Junior Summoner")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=2)
    assert scrys, "Expected scry 2 when a second Summoner is on field"


def test_apprentice_scholar_etb_scrys_2_and_gains_life():
    print("\n=== Apprentice Scholar: ETB scry 2 + life ===")
    game = Game()
    p1 = game.add_player("Alice")
    game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Apprentice Scholar")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=2)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) > 0]
    assert scrys, "Expected scry 2 on Apprentice Scholar ETB"
    assert gains, "Expected positive life-gain on Apprentice Scholar ETB"


def test_cadet_knight_attack_scrys_and_drains():
    print("\n=== Cadet Knight: attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ck = _put_on_battlefield(game, p1, "Cadet Knight")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': ck.id, 'attacker': ck.id, 'controller': p1.id},
                    source=ck.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys, "Expected scry on Cadet Knight attack"
    assert drains, "Expected -1 life on attack"


def test_trance_mage_etb_reveals_opp_hand():
    print("\n=== Trance Mage: ETB reveal hand ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Trance Mage")
    reveals = _events_after(game, before, EventType.REVEAL_HAND, player=p2.id)
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    assert scrys, "Expected scry on Trance Mage ETB"
    assert reveals, "Expected opp REVEAL_HAND on Trance Mage ETB"


def test_recruit_soldier_etb_scrys_and_drains():
    print("\n=== Recruit Soldier: ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Recruit Soldier")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and drains, "Expected scry + drain on Recruit Soldier ETB"


def test_pixie_mage_surveils_when_opp_has_threat():
    print("\n=== Pixie Mage: ETB surveil when opp has creature ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _put_on_battlefield(game, p2, "Goblin")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Pixie Mage")
    surveils = _events_after(game, before, EventType.SURVEIL, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert surveils, "Expected surveil 1 when opp has a creature"
    assert drains, "Expected -1 life on Pixie Mage ETB"


def test_royal_knight_attack_scrys_and_drains():
    print("\n=== Royal Knight: attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    rk = _put_on_battlefield(game, p1, "Royal Knight")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': rk.id, 'attacker': rk.id, 'controller': p1.id},
                    source=rk.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = [e for e in game.state.event_log[before:]
              if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id
              and e.payload.get('amount', 0) <= -1]
    assert scrys and drains, "Expected scry + drain on Royal Knight attack"


def test_black_chocobo_attack_scrys_and_drains():
    print("\n=== Black Chocobo: attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    bc = _put_on_battlefield(game, p1, "Black Chocobo")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': bc.id, 'attacker': bc.id, 'controller': p1.id},
                    source=bc.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and drains, "Expected scry + drain on Black Chocobo attack"


def test_moogle_knight_etb_scrys_and_gains_life():
    print("\n=== Moogle Knight: ETB scry + life ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Moogle Knight")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) >= 1]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and gains and drains, "Expected scry + gain + drain on Moogle Knight"


def test_behemoth_etb_scrys_and_drains_2():
    print("\n=== Behemoth: ETB scry + -2 drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Behemoth")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-2)
    assert scrys and drains, "Expected scry + -2 drain on Behemoth ETB"


def test_adamantoise_etb_scrys_2_and_gains_life():
    print("\n=== Adamantoise: ETB scry 2 + gain life ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Adamantoise")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=2)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) >= 2]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and gains and drains, "Expected scry 2 + life-gain + drain on Adamantoise ETB"


def test_ranger_etb_scrys_and_drains():
    print("\n=== Ranger: ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Ranger")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and drains, "Expected scry + drain on Ranger ETB"


def test_ninja_etb_reveals_hand_and_drains():
    print("\n=== Ninja: ETB reveal hand + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Ninja")
    reveals = _events_after(game, before, EventType.REVEAL_HAND, player=p2.id)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    assert scrys and reveals and drains, "Expected scry + reveal + drain on Ninja ETB"


def test_assassin_attack_reveals_hand_and_drains():
    print("\n=== Assassin: attack reveal + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    asn = _put_on_battlefield(game, p1, "Assassin")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': asn.id, 'attacker': asn.id, 'controller': p1.id},
                    source=asn.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    reveals = _events_after(game, before, EventType.REVEAL_HAND, player=p2.id)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and reveals and drains, "Expected scry + reveal + drain on Assassin attack"


def test_lich_attack_reveals_hand_and_drains():
    print("\n=== Lich: attack reveal + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    lich = _put_on_battlefield(game, p1, "Lich")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': lich.id, 'attacker': lich.id, 'controller': p1.id},
                    source=lich.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    surveils = _events_after(game, before, EventType.SURVEIL, player=p1.id, amount=1)
    reveals = _events_after(game, before, EventType.REVEAL_HAND, player=p2.id)
    drains = [e for e in game.state.event_log[before:]
              if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id
              and e.payload.get('amount', 0) <= -1]
    assert scrys and surveils and reveals and drains, (
        "Expected scry + surveil + reveal + drain on Lich attack")


def test_goblin_attack_scrys_and_drains():
    print("\n=== Goblin: attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    gob = _put_on_battlefield(game, p1, "Goblin")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': gob.id, 'attacker': gob.id, 'controller': p1.id},
                    source=gob.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and drains, "Expected scry + drain on Goblin attack"


def test_iron_giant_attack_scrys_and_drains():
    print("\n=== Iron Giant: attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    ig = _put_on_battlefield(game, p1, "Iron Giant")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': ig.id, 'attacker': ig.id, 'controller': p1.id},
                    source=ig.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and drains, "Expected scry + drain on Iron Giant attack"


def test_warrior_attack_scrys_and_drains():
    print("\n=== Warrior: attack scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    w = _put_on_battlefield(game, p1, "Warrior")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': w.id, 'attacker': w.id, 'controller': p1.id},
                    source=w.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and drains, "Expected scry + drain on Warrior attack"


def test_fighter_attack_scrys_gains_life_and_drains():
    print("\n=== Fighter: attack scry + gain + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    f = _put_on_battlefield(game, p1, "Fighter")
    before = len(game.state.event_log)
    game.emit(Event(type=EventType.ATTACK_DECLARED,
                    payload={'attacker_id': f.id, 'attacker': f.id, 'controller': p1.id},
                    source=f.id))
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) >= 1]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and gains and drains, "Expected scry + gain + drain on Fighter attack"


def test_chemist_etb_scrys_gains_life_and_drains():
    print("\n=== Chemist: ETB scry + gain + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Chemist")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) >= 1]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and gains and drains, "Expected scry + gain + drain on Chemist ETB"


def test_cure_mage_etb_scrys_gains_life_and_drains():
    print("\n=== Cure Mage: ETB scry + gain + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Cure Mage")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) >= 2]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and gains and drains, "Expected scry + +2 life + drain on Cure Mage ETB"


def test_sanctum_guardian_etb_scrys_gains_life_and_drains():
    print("\n=== Sanctum Guardian: ETB scry + gain + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Sanctum Guardian")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) >= 2]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and gains and drains, "Expected scry + +2 life + drain on Sanctum Guardian ETB"


def test_light_warrior_etb_scrys_gains_life_and_drains():
    print("\n=== Light Warrior: ETB scry + gain + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Light Warrior")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    gains = [e for e in game.state.event_log[before:]
             if e.type == EventType.LIFE_CHANGE
             and e.payload.get('player') == p1.id
             and e.payload.get('amount', 0) >= 1]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and gains and drains, "Expected scry + gain + drain on Light Warrior ETB"


def test_water_elemental_etb_scrys_2_surveils_and_drains():
    print("\n=== Water Elemental: ETB scry 2 + surveil + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Water Elemental")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=2)
    surveils = [e for e in game.state.event_log[before:]
                if e.type == EventType.SURVEIL
                and e.payload.get('player') == p1.id
                and e.payload.get('amount', 0) >= 1]
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert scrys and surveils and drains, "Expected scry 2 + surveil + drain on Water Elemental ETB"


def test_geomancer_etb_scrys_and_drains():
    print("\n=== Geomancer: ETB scry + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    _put_on_battlefield(game, p1, "Geomancer")
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id, amount=1)
    drains = [e for e in game.state.event_log[before:]
              if e.type == EventType.LIFE_CHANGE
              and e.payload.get('player') == p2.id
              and e.payload.get('amount', 0) <= -1]
    assert scrys and drains, "Expected scry + drain on Geomancer ETB"


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
