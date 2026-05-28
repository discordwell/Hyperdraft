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
from src.cards.custom import princess_catholicon as finc_module


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
# Balance-buff commons (commit 9e655dd4) — designed scry/drain cards
# ============================================================================
#
# These 8 commons (Cadet Mage, Junior Summoner, Apprentice Scholar, Cadet
# Knight, Trance Mage, Recruit Soldier, Pixie Mage, Royal Knight) were authored
# with genuine scry/gain/drain text — NOT slice-16 stub contamination — so
# their setups correctly match their rules text. Put the card on the
# battlefield, fire its trigger (ETB or ATTACK_DECLARED), assert the promised
# SCRY/SURVEIL + cross-controller event.


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


# ============================================================================
# Slice 5.5 — decision-axis flip (2026-05-19)
# ============================================================================
#
# Each new card surfaces a brand-new decision/state/zone/asymmetry/synergy
# fingerprint. Tests below verify the card LOADS and emits the right
# TARGET_REQUIRED / PendingChoice / asymmetry / synergy events at ETB or
# trigger-time. We do NOT resolve choices (resolution requires AI auto-pick
# or full UI plumbing) — we just confirm the decision-axis surface fires.

# ----------------------------------------------------------------------------
# 1. Cid Highwind, Sky-Engine Pilot — modal-only (3 modes, decision=2)
# ----------------------------------------------------------------------------

def test_cid_highwind_sky_engine_loads():
    """Loads as a legendary Human Pilot Engineer with a modal ETB interceptor."""
    print("\n=== Cid Highwind Sky-Engine: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cid = _put_on_battlefield(game, p1, "Cid Highwind, Sky-Engine Pilot")
    chars = cid.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Pilot' in chars.subtypes
    assert 'Engineer' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert cid.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(cid.interceptor_ids)}; subtypes={chars.subtypes}")


def test_cid_highwind_sky_engine_etb_opens_modal_choice():
    """ETB installs a modal_with_targeting PendingChoice with 3 modes."""
    print("\n=== Cid Highwind Sky-Engine: 3-mode choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    cid = _put_on_battlefield(game, p1, "Cid Highwind, Sky-Engine Pilot")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice after ETB"
    assert pc.source_id == cid.id
    assert pc.choice_type == "modal_with_targeting"
    assert len(pc.options) == 3, f"Expected 3 modes; got {len(pc.options)}"
    print(f"  Modes: {[opt.get('label') for opt in pc.options]}")


# ----------------------------------------------------------------------------
# 2. Cid Garlond, Magitek Architect — modal + cross-controller drain
# ----------------------------------------------------------------------------

def test_cid_garlond_magitek_loads():
    """Loads as a legendary Human Artificer Engineer with modal + cross ETBs."""
    print("\n=== Cid Garlond Magitek: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cid = _put_on_battlefield(game, p1, "Cid Garlond, Magitek Architect")
    chars = cid.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Artificer' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(cid.interceptor_ids) >= 2, (
        f"Expected >=2 interceptors (modal + drain companion); got {len(cid.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(cid.interceptor_ids)}")


def test_cid_garlond_magitek_etb_opens_modal_and_drains_each_opp():
    """ETB installs a 3-mode modal AND drains each opp 1 life."""
    print("\n=== Cid Garlond Magitek: modal + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    cid = _put_on_battlefield(game, p1, "Cid Garlond, Magitek Architect")
    pc = game.state.pending_choice
    assert pc is not None and pc.source_id == cid.id, (
        f"Expected pending_choice from Garlond ETB; got {pc}"
    )
    assert pc.choice_type == "modal_with_targeting"
    assert len(pc.options) == 3
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert drains, "Expected -1 life drain to each opp on Garlond ETB"
    print(f"  Modes: {len(pc.options)}; drains to p2: {len(drains)}")


# ----------------------------------------------------------------------------
# 3. Black Mage, Calamity Channeler — divided damage + cross drain
# ----------------------------------------------------------------------------

def test_black_mage_calamity_loads():
    """Loads as a Red enchantment with ETB interceptors."""
    print("\n=== Black Mage Calamity: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    bmc = _put_on_battlefield(game, p1, "Black Mage, Calamity Channeler")
    assert CardType.ENCHANTMENT in bmc.characteristics.types
    assert len(bmc.interceptor_ids) >= 2, "Expected divided-damage + drain ETBs"
    print(f"  Interceptors: {len(bmc.interceptor_ids)}")


def test_black_mage_calamity_etb_emits_divided_damage_5_and_drains_each_opp():
    """ETB emits TARGET_REQUIRED with divide_amount=5 + LIFE_CHANGE for opp."""
    print("\n=== Black Mage Calamity: divided 5 + drain ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    before = len(game.state.event_log)
    bmc = _put_on_battlefield(game, p1, "Black Mage, Calamity Channeler")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == bmc.id
        and e.payload.get('effect') == 'damage'
        and e.payload.get('divide_amount') == 5
    ]
    assert target_reqs, (
        f"Expected damage TARGET_REQUIRED with divide_amount=5; got "
        f"{[(e.type.name, e.payload.get('effect'), e.payload.get('divide_amount')) for e in new[-10:]]}"
    )
    drains = _events_after(game, before, EventType.LIFE_CHANGE, player=p2.id, amount=-1)
    assert drains, "Expected -1 life to each opp"
    print(f"  divided 5 to {target_reqs[0].payload.get('max_targets')} targets; opp drain: {len(drains)}")


# ----------------------------------------------------------------------------
# 4. White Mage, Trinity Healing — divided counters + creatures_you_control
# ----------------------------------------------------------------------------

def test_white_mage_trinity_loads():
    """Loads as a White Mage Cleric with an ETB interceptor."""
    print("\n=== White Mage Trinity: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    wmt = _put_on_battlefield(game, p1, "White Mage, Trinity Healing")
    chars = wmt.characteristics
    assert CardType.CREATURE in chars.types
    assert 'White Mage' in chars.subtypes
    assert wmt.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(wmt.interceptor_ids)}")


def test_white_mage_trinity_etb_emits_counter_distribute_target_required():
    """ETB emits TARGET_REQUIRED with effect=counter_add and divide_amount=3."""
    print("\n=== White Mage Trinity: distribute counters ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    wmt = _put_on_battlefield(game, p1, "White Mage, Trinity Healing")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == wmt.id
        and e.payload.get('effect') == 'counter_add'
    ]
    assert target_reqs, (
        f"Expected counter_add TARGET_REQUIRED; got {[(e.type.name, e.payload.get('effect')) for e in new[-10:]]}"
    )
    payload = target_reqs[0].payload
    assert payload.get('divide_amount') == 3, (
        f"Expected divide_amount=3; got {payload.get('divide_amount')}"
    )
    assert payload.get('target_filter') == 'your_creature'
    print(f"  divide_amount: {payload.get('divide_amount')}; filter: {payload.get('target_filter')}")


# ----------------------------------------------------------------------------
# 5. Sephiroth, Reunion Catalyst — targeted death + REVEAL_HAND info pulse
# ----------------------------------------------------------------------------

def test_sephiroth_reunion_loads():
    """Loads as a legendary Human SOLDIER with death-trigger interceptors."""
    print("\n=== Sephiroth Reunion: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    seph = _put_on_battlefield(game, p1, "Sephiroth, Reunion Catalyst")
    chars = seph.characteristics
    assert CardType.CREATURE in chars.types
    assert 'SOLDIER' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(seph.interceptor_ids) >= 2, (
        f"Expected >=2 (targeted death + companion); got {len(seph.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(seph.interceptor_ids)}")


def test_sephiroth_reunion_death_emits_target_required_and_reveal_hand():
    """On death: TARGET_REQUIRED to exile opp creature + REVEAL_HAND each opp."""
    print("\n=== Sephiroth Reunion: death exile + reveal ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    seph = _put_on_battlefield(game, p1, "Sephiroth, Reunion Catalyst")
    before = len(game.state.event_log)
    # Simulate death: ZONE_CHANGE battlefield -> graveyard.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': seph.id,
            'from_zone': 'battlefield',
            'to_zone': f'graveyard_{p1.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
            'reason': 'destroy',
        },
        source=seph.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == seph.id
        and e.payload.get('effect') == 'exile'
    ]
    assert target_reqs, f"Expected exile TARGET_REQUIRED on death; got {[(e.type.name, e.payload.get('effect')) for e in new[-10:]]}"
    assert target_reqs[0].payload.get('target_filter') == 'opponent_creature'
    reveals = [
        e for e in new
        if e.type == EventType.REVEAL_HAND
        and e.payload.get('player') == p2.id
        and e.source == seph.id
    ]
    assert reveals, "Expected REVEAL_HAND on each opp on Sephiroth death"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; REVEAL_HAND: {len(reveals)}")


# ----------------------------------------------------------------------------
# 6. Cloud Strife, Limit Break Edge — targeted attack + tribal counter
# ----------------------------------------------------------------------------

def test_cloud_strife_omnislash_loads():
    """Loads as a legendary Human SOLDIER Mercenary with attack interceptors."""
    print("\n=== Cloud Strife Omnislash: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cloud = _put_on_battlefield(game, p1, "Cloud Strife, Limit Break Edge")
    chars = cloud.characteristics
    assert CardType.CREATURE in chars.types
    assert 'SOLDIER' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(cloud.interceptor_ids) >= 2, (
        f"Expected >=2 (targeted attack + companion); got {len(cloud.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(cloud.interceptor_ids)}")


def test_cloud_strife_omnislash_attack_emits_tap_target_required():
    """On attack: TARGET_REQUIRED with effect='tap' targeting opp creature."""
    print("\n=== Cloud Strife Omnislash: tap on attack ===")
    game = Game()
    p1 = game.add_player("Alice")
    cloud = _put_on_battlefield(game, p1, "Cloud Strife, Limit Break Edge")
    before = len(game.state.event_log)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': cloud.id, 'attacker': cloud.id, 'controller': p1.id},
        source=cloud.id,
    ))
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == cloud.id
        and e.payload.get('effect') == 'tap'
    ]
    assert target_reqs, f"Expected tap TARGET_REQUIRED; got {[(e.type.name, e.payload.get('effect')) for e in new[-10:]]}"
    assert target_reqs[0].payload.get('target_filter') == 'opponent_creature'
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; effect=tap; filter=opponent_creature")


# ----------------------------------------------------------------------------
# 7. Yuna's Sending Ritual — top-N land pick + graveyard zone-scaling
# ----------------------------------------------------------------------------

def test_yuna_sending_ritual_loads():
    """Loads as a Green/White enchantment with ETB interceptor."""
    print("\n=== Yuna's Sending Ritual: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    ysr = _put_on_battlefield(game, p1, "Yuna's Sending Ritual")
    assert CardType.ENCHANTMENT in ysr.characteristics.types
    assert ysr.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(ysr.interceptor_ids)}")


def test_yuna_sending_ritual_with_library_lands_opens_choice():
    """ETB with a land on top of library installs a PendingChoice."""
    print("\n=== Yuna's Sending Ritual: library lands -> choice ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a land in p1's library so the top-N helper has something to pick.
    lib = game.state.zones[f'library_{p1.id}']
    from src.engine import Characteristics
    land_chars = Characteristics(types={CardType.LAND}, subtypes={"Forest"})
    land_obj = game.create_object(
        name="Test Forest", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=land_chars, card_def=None,
    )
    if land_obj.id not in lib.objects:
        lib.objects.append(land_obj.id)
    ysr = _put_on_battlefield(game, p1, "Yuna's Sending Ritual")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice from top-N land pick"
    assert pc.source_id == ysr.id, f"Choice source should be Yuna's Sending; got {pc.source_id}"
    print(f"  PendingChoice type: {pc.choice_type}; source: {pc.source_id}")


def test_yuna_sending_ritual_empty_library_no_op():
    """ETB with empty library doesn't crash."""
    print("\n=== Yuna's Sending Ritual: empty library no-op ===")
    game = Game()
    p1 = game.add_player("Alice")
    ysr = _put_on_battlefield(game, p1, "Yuna's Sending Ritual")
    assert ysr.zone == ZoneType.BATTLEFIELD
    print(f"  No-crash on empty library; zone={ysr.zone}")


# ----------------------------------------------------------------------------
# 8. Cid Pollendina, Adamant Smith — library search ETB (creature)
# ----------------------------------------------------------------------------

def test_cid_pollendina_adamant_loads():
    """Loads as a legendary Human Artificer Engineer with ETB interceptors."""
    print("\n=== Cid Pollendina Adamant: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    cid = _put_on_battlefield(game, p1, "Cid Pollendina, Adamant Smith")
    chars = cid.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Artificer' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert cid.interceptor_ids, "Expected ETB interceptor"
    print(f"  Interceptors: {len(cid.interceptor_ids)}")


def test_cid_pollendina_adamant_etb_opens_library_search():
    """ETB installs a library-search PendingChoice (when library has cards)."""
    print("\n=== Cid Pollendina Adamant: library search ===")
    game = Game()
    p1 = game.add_player("Alice")
    # Plant a creature in p1's library so the tutor has a target.
    lib = game.state.zones[f'library_{p1.id}']
    from src.engine import Characteristics
    creature_chars = Characteristics(
        types={CardType.CREATURE}, subtypes={"Beast"}, power=2, toughness=2,
    )
    creat_obj = game.create_object(
        name="Forge Mascot", owner_id=p1.id, zone=ZoneType.LIBRARY,
        characteristics=creature_chars, card_def=None,
    )
    if creat_obj.id not in lib.objects:
        lib.objects.append(creat_obj.id)
    cid = _put_on_battlefield(game, p1, "Cid Pollendina, Adamant Smith")
    pc = game.state.pending_choice
    assert pc is not None, "Expected pending_choice from library search"
    assert pc.source_id == cid.id, f"Source should be Cid; got {pc.source_id}"
    print(f"  PendingChoice type: {pc.choice_type}; options: {len(pc.options)}")


# ----------------------------------------------------------------------------
# 9. Tifa, Final Heaven Master — targeted ETB pump + SCRY by tribe count
# ----------------------------------------------------------------------------

def test_tifa_final_heaven_loads():
    """Loads as a legendary Monk Warrior with ETB interceptors."""
    print("\n=== Tifa Final Heaven Master: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    tifa = _put_on_battlefield(game, p1, "Tifa, Final Heaven Master")
    chars = tifa.characteristics
    assert CardType.CREATURE in chars.types
    assert 'Monk' in chars.subtypes
    assert 'Legendary' in (chars.supertypes or set())
    assert len(tifa.interceptor_ids) >= 2, (
        f"Expected >=2 (targeted pump + scry companion); got {len(tifa.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(tifa.interceptor_ids)}")


def test_tifa_final_heaven_etb_emits_pump_target_required_and_scry():
    """ETB: TARGET_REQUIRED with effect=pump + SCRY emission."""
    print("\n=== Tifa Final Heaven: pump + scry ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    tifa = _put_on_battlefield(game, p1, "Tifa, Final Heaven Master")
    new = game.state.event_log[before:]
    target_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == tifa.id
        and e.payload.get('effect') == 'pump'
    ]
    assert target_reqs, f"Expected pump TARGET_REQUIRED; got {[(e.type.name, e.payload.get('effect')) for e in new[-10:]]}"
    assert target_reqs[0].payload.get('target_filter') == 'your_creature'
    scrys = _events_after(game, before, EventType.SCRY, player=p1.id)
    assert scrys, "Expected SCRY on Tifa ETB"
    print(f"  TARGET_REQUIRED: {len(target_reqs)}; SCRY: {len(scrys)}")


# ----------------------------------------------------------------------------
# 10. Materia Mastery, Limit Crescendo — modal + targeted (decision=3)
# ----------------------------------------------------------------------------

def test_materia_mastery_crescendo_loads():
    """Loads as a 3-color enchantment with modal + targeted ETBs."""
    print("\n=== Materia Mastery Crescendo: load ===")
    game = Game()
    p1 = game.add_player("Alice")
    mmc = _put_on_battlefield(game, p1, "Materia Mastery, Limit Crescendo")
    assert CardType.ENCHANTMENT in mmc.characteristics.types
    assert len(mmc.interceptor_ids) >= 2, (
        f"Expected >=2 (modal + targeted); got {len(mmc.interceptor_ids)}"
    )
    print(f"  Interceptors: {len(mmc.interceptor_ids)}")


def test_materia_mastery_crescendo_etb_emits_modal_and_pump_target_required():
    """ETB: opens modal_with_targeting PendingChoice AND emits pump TARGET_REQUIRED."""
    print("\n=== Materia Mastery Crescendo: modal + pump ===")
    game = Game()
    p1 = game.add_player("Alice")
    before = len(game.state.event_log)
    mmc = _put_on_battlefield(game, p1, "Materia Mastery, Limit Crescendo")
    pc = game.state.pending_choice
    # The pending_choice will be the LAST modal/target one installed — depending
    # on order it could be the targeted pump or the modal. Either way one
    # PendingChoice exists.
    assert pc is not None, "Expected pending_choice from Materia Mastery ETB"
    assert pc.source_id == mmc.id, f"Choice source should be Materia Mastery; got {pc.source_id}"
    new = game.state.event_log[before:]
    pump_reqs = [
        e for e in new
        if e.type == EventType.TARGET_REQUIRED
        and e.payload.get('source') == mmc.id
        and e.payload.get('effect') == 'pump'
    ]
    assert pump_reqs, "Expected pump TARGET_REQUIRED from Materia Mastery"
    print(f"  PendingChoice type: {pc.choice_type}; pump TARGET_REQUIRED: {len(pump_reqs)}")


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
