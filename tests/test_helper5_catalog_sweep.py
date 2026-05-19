"""Helper 5 catalog sweep — 14 Equipment rewires across 11 custom sets.

Mirrors the pattern in tests/test_attach_granted_triggered.py: attach the
Equipment to a creature, fire a combat DAMAGE event, and assert the expected
downstream event(s) appear in the event log.

Coverage map (per rewired card):
  AOT: Thunder Spear (deals combat damage to Titan → destroy that Titan)
  DMS: Tengen's Cleavers (combat damage to player → draw a card)
  DMS: Shinobu's Stinger (damage to creature → 2x -1/-1 counters)
  JJK: Playful Cloud (combat damage → untap equipped creature)
  JJK: Split Soul Katana (combat damage to player → discard)
  JJK: Festering Life Sword (damage → controller gains that much life)
  MHA: Bakugo's Grenade Gauntlets (combat damage to player → 2 grenade damage)
  NRT: Samehada (combat damage to player → controller gains that much life)
  OP:  Clima-Tact (combat damage to player → tap one of their creatures)
  SW:  Slave Tracker (combat damage to player → scry 2)
  PA:  Azula's Crown (combat damage to player → discard)
  TH:  Temporal Blade (combat damage to player → time counter)
  PC:  Mage Masher (combat damage to player → random discard)
  MOP: Shock Gauntlets (combat damage to player → tap one of their creatures)
  MVL: Chitauri Scepter (combat damage to player → threaten one of their creatures)
  SGW: Crystal Necklace (combat damage to player → scry 1)

Plus 3 edge-case tests:
  - Revoke on UNATTACH
  - No fire on non-combat damage (for cards that filter combat=True)
  - No fire when wrong creature deals the damage (target_id binding)
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    make_creature,
)


def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put_card(game, owner, card_def, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _plain_creature(name="Plain 1/1", subtypes=None):
    return make_creature(
        name=name,
        power=2, toughness=2, mana_cost="{2}",
        colors=set(), subtypes=set(subtypes) if subtypes else {"Human"},
        text="",
    )


def _attach(game, equip_obj, target_obj):
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': equip_obj.id, 'target_id': target_obj.id},
        source=equip_obj.id,
    ))


def _combat_dmg(game, attacker_obj, victim_id, amount=2):
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': attacker_obj.id,
            'target': victim_id,
            'amount': amount,
            'combat': True,
        },
        source=attacker_obj.id,
    ))


def _has_event(game, event_type, **payload_match):
    for e in game.state.event_log:
        if e.type != event_type:
            continue
        ok = True
        for k, v in payload_match.items():
            if e.payload.get(k) != v:
                ok = False
                break
        if ok:
            return True
    return False


# =============================================================================
# Per-card positive-path tests
# =============================================================================

def test_aot_thunder_spear_destroys_titan_on_combat():
    from src.cards.custom.attack_on_titan import THUNDER_SPEAR
    game, p1, p2 = _new_game()
    spear = _put_card(game, p1, THUNDER_SPEAR)
    attacker = _put_card(game, p1, _plain_creature("Scout"))
    titan = _put_card(game, p2, _plain_creature("Some Titan", subtypes={"Titan"}))
    _attach(game, spear, attacker)
    _combat_dmg(game, attacker, titan.id, amount=4)
    # The granted trigger emits DESTROY; the pipeline consumes it and the
    # canonical "destroyed" emission downstream is OBJECT_DESTROYED. Either
    # is acceptable confirmation that the trigger fired.
    destroyed = (
        _has_event(game, EventType.DESTROY, object_id=titan.id)
        or _has_event(game, EventType.OBJECT_DESTROYED, object_id=titan.id)
    )
    assert destroyed, (
        f"Thunder Spear should emit DESTROY (or OBJECT_DESTROYED) on the Titan; "
        f"recent={[e.type.name for e in game.state.event_log[-8:]]}"
    )


def test_dms_tengens_cleavers_draws_on_combat_to_player():
    from src.cards.custom.demon_slayer import TENGENS_CLEAVERS
    game, p1, p2 = _new_game()
    cleavers = _put_card(game, p1, TENGENS_CLEAVERS)
    attacker = _put_card(game, p1, _plain_creature("Slayer"))
    _attach(game, cleavers, attacker)
    _combat_dmg(game, attacker, p2.id, amount=3)
    assert _has_event(game, EventType.DRAW, player=p1.id, amount=1), (
        "Tengen's Cleavers should fire a DRAW for the equipped creature's controller"
    )


def test_dms_shinobus_stinger_adds_counters_on_creature_dmg():
    from src.cards.custom.demon_slayer import SHINOBUS_STINGER
    game, p1, p2 = _new_game()
    stinger = _put_card(game, p1, SHINOBUS_STINGER)
    attacker = _put_card(game, p1, _plain_creature("Insect Pillar"))
    victim_creature = _put_card(game, p2, _plain_creature("Demon", subtypes={"Demon"}))
    _attach(game, stinger, attacker)
    _combat_dmg(game, attacker, victim_creature.id, amount=2)
    assert _has_event(
        game, EventType.COUNTER_ADDED,
        object_id=victim_creature.id, counter_type='-1/-1', amount=2,
    ), "Shinobu's Stinger should add 2x -1/-1 counters on damaged creature"


def test_jjk_playful_cloud_untaps_on_combat_dmg():
    from src.cards.custom.jujutsu_kaisen import PLAYFUL_CLOUD
    game, p1, p2 = _new_game()
    cloud = _put_card(game, p1, PLAYFUL_CLOUD)
    attacker = _put_card(game, p1, _plain_creature("Sorcerer"))
    _attach(game, cloud, attacker)
    _combat_dmg(game, attacker, p2.id, amount=3)
    assert _has_event(game, EventType.UNTAP, object_id=attacker.id), (
        "Playful Cloud should fire an UNTAP on the equipped creature"
    )


def test_jjk_split_soul_katana_discards_on_combat_to_player():
    from src.cards.custom.jujutsu_kaisen import SPLIT_SOUL_KATANA
    game, p1, p2 = _new_game()
    katana = _put_card(game, p1, SPLIT_SOUL_KATANA)
    attacker = _put_card(game, p1, _plain_creature("Sorcerer"))
    _attach(game, katana, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    assert _has_event(game, EventType.DISCARD, player=p2.id, amount=1), (
        "Split Soul Katana should fire a DISCARD on the struck player"
    )


def test_jjk_festering_life_sword_gains_life_on_any_damage():
    from src.cards.custom.jujutsu_kaisen import FESTERING_LIFE_SWORD
    game, p1, p2 = _new_game()
    sword = _put_card(game, p1, FESTERING_LIFE_SWORD)
    attacker = _put_card(game, p1, _plain_creature("Sorcerer"))
    _attach(game, sword, attacker)
    _combat_dmg(game, attacker, p2.id, amount=4)
    assert _has_event(game, EventType.LIFE_CHANGE, player=p1.id, amount=4), (
        "Festering Life Sword should gain controller 4 life equal to damage dealt"
    )


def test_mha_bakugo_gauntlets_emits_grenade_damage():
    from src.cards.custom.my_hero_academia import BAKUGO_GAUNTLETS
    game, p1, p2 = _new_game()
    gauntlets = _put_card(game, p1, BAKUGO_GAUNTLETS)
    attacker = _put_card(game, p1, _plain_creature("Hero"))
    _attach(game, gauntlets, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    # Look for the *secondary* non-combat 2-damage emission.
    grenade = [
        e for e in game.state.event_log
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 2
        and not e.payload.get('combat', False)
    ]
    assert grenade, (
        f"Bakugo's Gauntlets should emit a non-combat 2 DAMAGE on the struck "
        f"player; recent={[(e.type.name, e.payload.get('amount'), e.payload.get('combat')) for e in game.state.event_log[-10:]]}"
    )


def test_nrt_samehada_gains_life_on_combat_to_player():
    from src.cards.custom.naruto import SAMEHADA
    game, p1, p2 = _new_game()
    samehada = _put_card(game, p1, SAMEHADA)
    attacker = _put_card(game, p1, _plain_creature("Ninja"))
    _attach(game, samehada, attacker)
    _combat_dmg(game, attacker, p2.id, amount=5)
    assert _has_event(game, EventType.LIFE_CHANGE, player=p1.id, amount=5), (
        "Samehada should gain controller life equal to combat damage dealt to player"
    )


def test_op_clima_tact_taps_victim_creature_on_combat_to_player():
    from src.cards.custom.one_piece import CLIMA_TACT
    game, p1, p2 = _new_game()
    clima = _put_card(game, p1, CLIMA_TACT)
    attacker = _put_card(game, p1, _plain_creature("Pirate"))
    victim_target = _put_card(game, p2, _plain_creature("Marine"))
    _attach(game, clima, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    assert _has_event(game, EventType.TAP, object_id=victim_target.id), (
        "Clima-Tact should tap the victim's creature"
    )


def test_sw_slave_tracker_scrys_2_on_combat_to_player():
    from src.cards.custom.star_wars import SLAVE_TRACKER
    game, p1, p2 = _new_game()
    tracker = _put_card(game, p1, SLAVE_TRACKER)
    attacker = _put_card(game, p1, _plain_creature("Bounty Hunter"))
    _attach(game, tracker, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    scrys = [
        e for e in game.state.event_log
        if e.type == EventType.ACTIVATE
        and e.payload.get('action') == 'scry'
        and e.payload.get('amount') == 2
        and e.payload.get('player') == p1.id
    ]
    assert scrys, "Slave Tracker should emit ACTIVATE(action=scry, amount=2) for p1"


def test_pa_azulas_crown_discards_on_combat_to_player():
    from src.cards.custom.penultimate_avatar import AZULAS_CROWN
    game, p1, p2 = _new_game()
    crown = _put_card(game, p1, AZULAS_CROWN)
    attacker = _put_card(game, p1, _plain_creature("Firebender"))
    _attach(game, crown, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    assert _has_event(game, EventType.DISCARD, player=p2.id, amount=1), (
        "Azula's Crown should fire DISCARD on the struck player"
    )


def test_th_temporal_blade_adds_time_counter_on_combat_to_player():
    from src.cards.custom.temporal_horizons import TEMPORAL_BLADE
    game, p1, p2 = _new_game()
    blade = _put_card(game, p1, TEMPORAL_BLADE)
    attacker = _put_card(game, p1, _plain_creature("Time Knight"))
    victim_perm = _put_card(game, p2, _plain_creature("Mox"))
    _attach(game, blade, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    assert _has_event(
        game, EventType.COUNTER_ADDED,
        object_id=victim_perm.id, counter_type='time', amount=1,
    ), "Temporal Blade should add a time counter to a permanent the victim controls"


def test_pc_mage_masher_random_discards_on_combat_to_player():
    from src.cards.custom.princess_catholicon import MAGE_MASHER
    game, p1, p2 = _new_game()
    masher = _put_card(game, p1, MAGE_MASHER)
    attacker = _put_card(game, p1, _plain_creature("Knight"))
    _attach(game, masher, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    discards = [
        e for e in game.state.event_log
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
        and e.payload.get('random', False)
    ]
    assert discards, "Mage Masher should fire a random DISCARD on the struck player"


def test_mop_shock_gauntlets_taps_victim_creature_on_combat():
    from src.cards.custom.man_of_pider import SHOCK_GAUNTLETS
    game, p1, p2 = _new_game()
    gauntlets = _put_card(game, p1, SHOCK_GAUNTLETS)
    attacker = _put_card(game, p1, _plain_creature("Spider"))
    victim_creature = _put_card(game, p2, _plain_creature("Goon"))
    _attach(game, gauntlets, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    assert _has_event(game, EventType.TAP, object_id=victim_creature.id), (
        "Shock Gauntlets should tap the victim's creature"
    )


def test_mvl_chitauri_scepter_threatens_victim_creature_on_combat():
    from src.cards.custom.marvel_avengers import CHITAURI_SCEPTER
    game, p1, p2 = _new_game()
    scepter = _put_card(game, p1, CHITAURI_SCEPTER)
    attacker = _put_card(game, p1, _plain_creature("Avenger"))
    victim_creature = _put_card(game, p2, _plain_creature("Chitauri"))
    _attach(game, scepter, attacker)
    _combat_dmg(game, attacker, p2.id, amount=2)
    # threaten_creature() emits CONTROL_CHANGE + UNTAP + GRANT_KEYWORD haste.
    assert _has_event(
        game, EventType.CONTROL_CHANGE,
        object_id=victim_creature.id, new_controller=p1.id,
    ), "Chitauri Scepter should emit CONTROL_CHANGE on the victim's creature"


def test_sgw_crystal_necklace_scrys_1_on_combat_to_player():
    from src.cards.custom.studio_ghibli import CRYSTAL_NECKLACE
    game, p1, p2 = _new_game()
    necklace = _put_card(game, p1, CRYSTAL_NECKLACE)
    attacker = _put_card(game, p1, _plain_creature("Spirit"))
    _attach(game, necklace, attacker)
    _combat_dmg(game, attacker, p2.id, amount=1)
    scrys = [
        e for e in game.state.event_log
        if e.type == EventType.ACTIVATE
        and e.payload.get('action') == 'scry'
        and e.payload.get('amount') == 1
        and e.payload.get('player') == p1.id
    ]
    assert scrys, "Crystal Necklace should emit ACTIVATE(action=scry, amount=1)"


# =============================================================================
# Edge cases
# =============================================================================

def test_edge_unattach_revokes_grant():
    """Unattaching should pop the granted trigger; subsequent damage shouldn't fire."""
    from src.cards.custom.naruto import SAMEHADA
    game, p1, p2 = _new_game()
    samehada = _put_card(game, p1, SAMEHADA)
    attacker = _put_card(game, p1, _plain_creature("Ninja"))
    _attach(game, samehada, attacker)
    game.emit(Event(
        type=EventType.UNATTACH,
        payload={'object_id': samehada.id, 'target_id': attacker.id},
        source=samehada.id,
    ))
    p1_life_before = p1.life
    _combat_dmg(game, attacker, p2.id, amount=5)
    # Should NOT see a life gain LIFE_CHANGE keyed to p1
    p1_gains = [
        e for e in game.state.event_log
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount', 0) > 0
    ]
    assert not p1_gains, (
        f"After UNATTACH, Samehada should not fire — p1 life {p1_life_before}→{p1.life}; "
        f"unexpected gains: {p1_gains}"
    )


def test_edge_non_combat_damage_does_not_fire_combat_filter():
    """Tengen's Cleavers requires combat=True. Non-combat damage shouldn't fire."""
    from src.cards.custom.demon_slayer import TENGENS_CLEAVERS
    game, p1, p2 = _new_game()
    cleavers = _put_card(game, p1, TENGENS_CLEAVERS)
    attacker = _put_card(game, p1, _plain_creature("Slayer"))
    _attach(game, cleavers, attacker)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': attacker.id,
            'target': p2.id,
            'amount': 3,
            'combat': False,  # ← non-combat
        },
        source=attacker.id,
    ))
    draws = [
        e for e in game.state.event_log
        if e.type == EventType.DRAW
        and e.payload.get('player') == p1.id
    ]
    assert not draws, "Tengen's Cleavers should NOT fire on non-combat damage"


def test_edge_wrong_creature_does_not_trigger_grant():
    """The granted trigger targets the equipped creature only — damage from
    another, unrelated creature must not fire it."""
    from src.cards.custom.jujutsu_kaisen import SPLIT_SOUL_KATANA
    game, p1, p2 = _new_game()
    katana = _put_card(game, p1, SPLIT_SOUL_KATANA)
    equipped = _put_card(game, p1, _plain_creature("Sorcerer"))
    other = _put_card(game, p1, _plain_creature("Other Sorcerer"))
    _attach(game, katana, equipped)
    # Damage source = `other`, not `equipped`.
    _combat_dmg(game, other, p2.id, amount=2)
    discards = [
        e for e in game.state.event_log
        if e.type == EventType.DISCARD
        and e.payload.get('player') == p2.id
    ]
    assert not discards, (
        "Split Soul Katana should NOT fire when an unrelated creature deals damage"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("Helper 5 catalog sweep — 14 Equipment rewires across 11 custom sets")
    print("=" * 70)
    tests = [
        # Per-card
        test_aot_thunder_spear_destroys_titan_on_combat,
        test_dms_tengens_cleavers_draws_on_combat_to_player,
        test_dms_shinobus_stinger_adds_counters_on_creature_dmg,
        test_jjk_playful_cloud_untaps_on_combat_dmg,
        test_jjk_split_soul_katana_discards_on_combat_to_player,
        test_jjk_festering_life_sword_gains_life_on_any_damage,
        test_mha_bakugo_gauntlets_emits_grenade_damage,
        test_nrt_samehada_gains_life_on_combat_to_player,
        test_op_clima_tact_taps_victim_creature_on_combat_to_player,
        test_sw_slave_tracker_scrys_2_on_combat_to_player,
        test_pa_azulas_crown_discards_on_combat_to_player,
        test_th_temporal_blade_adds_time_counter_on_combat_to_player,
        test_pc_mage_masher_random_discards_on_combat_to_player,
        test_mop_shock_gauntlets_taps_victim_creature_on_combat,
        test_mvl_chitauri_scepter_threatens_victim_creature_on_combat,
        test_sgw_crystal_necklace_scrys_1_on_combat_to_player,
        # Edge cases
        test_edge_unattach_revokes_grant,
        test_edge_non_combat_damage_does_not_fire_combat_filter,
        test_edge_wrong_creature_does_not_trigger_grant,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print("=" * 70)
    print(f"Total: {passed}/{len(tests)} passed")
    print("=" * 70)
