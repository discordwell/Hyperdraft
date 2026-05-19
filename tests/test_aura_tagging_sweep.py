"""Aura tagging sweep — catalog-wide pass to add subtypes={"Aura"} to
crossover-set Auras that were previously written as plain Enchantments.

Agent A40 in W22+ surveyed every `make_enchantment(...)` whose text mentions
"enchanted creature" / "enchanted land" / "enchanted player" / etc. across
the custom-set directory (excluding `legend_of_zelda.py`, which has a
parallel surgical sweep). Roughly 30% of those Auras were correctly written
but lacked the `subtypes={"Aura"}` tag — the engine's ATTACH event never
fires for them, so `make_aura_setup` (Helper 5) is unreachable.

This file exercises two layers:

  **List A (pure tagging fixes, 37 cards):** assert that the Aura subtype
  is present on each card's characteristics. Tagging alone is enough to
  let the engine identify these as Auras for ATTACH/UNATTACH; existing
  non-Helper-5 setup_interceptors (e.g. stub etb_effects) keep working.

  **List B (tagged + Helper 5 wired, 6 cards):** mirror the
  `tests/test_helper5_catalog_sweep.py` pattern — attach the Aura to a
  creature, fire the triggering event, and assert the expected downstream
  event(s) appear in the event log.

Coverage by set:
  DMS: 7 tag-only, 2 wired (Blazing Rage: attack→1 dmg, Serpent Coils:
       combat dmg to creature → tap)
  DBZ: 2 tag-only
  LWN: 7 tag-only, 1 wired (Morcant's Eyes: combat dmg to player → draw)
  MOP: 3 tag-only
  MHA: 4 tag-only, 2 wired (Hero License: combat dmg to player → +2 life,
       Explosive Power: attack → 1 dmg)
  NRT: 3 tag-only
  PA:  3 tag-only, 1 wired (Dark Spirit's Blessing: enchanted creature
       dies → each opponent loses 2 life)
  POK: 1 tag-only
  PCT: 6 tag-only
  TH:  1 tag-only
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
    make_creature,
)


# =============================================================================
# Test helpers — mirror tests/test_helper5_catalog_sweep.py
# =============================================================================

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


def _attach(game, aura_obj, target_obj):
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura_obj.id, 'target_id': target_obj.id},
        source=aura_obj.id,
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
# List A — pure tagging fixes (assert Aura subtype is present)
# =============================================================================

def test_dms_tag_ubuyashiki_blessing_is_aura():
    from src.cards.custom.demon_slayer import UBUYASHIKI_BLESSING
    assert "Aura" in UBUYASHIKI_BLESSING.characteristics.subtypes


def test_dms_tag_mist_breathing_form_is_aura():
    from src.cards.custom.demon_slayer import MIST_BREATHING_FORM
    assert "Aura" in MIST_BREATHING_FORM.characteristics.subtypes


def test_dms_tag_thunder_breathing_form_is_aura():
    from src.cards.custom.demon_slayer import THUNDER_BREATHING_FORM
    assert "Aura" in THUNDER_BREATHING_FORM.characteristics.subtypes


def test_dms_tag_serpent_breathing_form_is_aura():
    from src.cards.custom.demon_slayer import SERPENT_BREATHING_FORM
    assert "Aura" in SERPENT_BREATHING_FORM.characteristics.subtypes


def test_dms_tag_wild_instinct_is_aura():
    from src.cards.custom.demon_slayer import WILD_INSTINCT
    assert "Aura" in WILD_INSTINCT.characteristics.subtypes


def test_dms_tag_demon_blood_frenzy_is_aura():
    from src.cards.custom.demon_slayer import DEMON_BLOOD_FRENZY
    assert "Aura" in DEMON_BLOOD_FRENZY.characteristics.subtypes


def test_dms_tag_lightning_reflexes_is_aura():
    from src.cards.custom.demon_slayer import LIGHTNING_REFLEXES
    assert "Aura" in LIGHTNING_REFLEXES.characteristics.subtypes


def test_dbz_tag_majin_mark_is_aura():
    from src.cards.custom.dragon_ball import MAJIN_MARK
    assert "Aura" in MAJIN_MARK.characteristics.subtypes


def test_dbz_tag_super_saiyan_aura_is_aura():
    from src.cards.custom.dragon_ball import SUPER_SAIYAN_AURA
    assert "Aura" in SUPER_SAIYAN_AURA.characteristics.subtypes


def test_lwn_tag_aquitects_defenses_is_aura():
    from src.cards.custom.lorwyn_custom import AQUITECTS_DEFENSES
    assert "Aura" in AQUITECTS_DEFENSES.characteristics.subtypes


def test_lwn_tag_blossombind_is_aura():
    from src.cards.custom.lorwyn_custom import BLOSSOMBIND
    assert "Aura" in BLOSSOMBIND.characteristics.subtypes


def test_lwn_tag_evershrikes_gift_is_aura():
    from src.cards.custom.lorwyn_custom import EVERSHRIKES_GIFT
    assert "Aura" in EVERSHRIKES_GIFT.characteristics.subtypes


def test_lwn_tag_gilt_leafs_embrace_is_aura():
    from src.cards.custom.lorwyn_custom import GILT_LEAFS_EMBRACE
    assert "Aura" in GILT_LEAFS_EMBRACE.characteristics.subtypes


def test_lwn_tag_pitiless_fists_is_aura():
    from src.cards.custom.lorwyn_custom import PITILESS_FISTS
    assert "Aura" in PITILESS_FISTS.characteristics.subtypes


def test_lwn_tag_shimmerwilds_growth_is_aura():
    from src.cards.custom.lorwyn_custom import SHIMMERWILDS_GROWTH
    assert "Aura" in SHIMMERWILDS_GROWTH.characteristics.subtypes


def test_lwn_tag_nettlevine_blight_is_aura():
    from src.cards.custom.lorwyn_custom import NETTLEVINE_BLIGHT
    assert "Aura" in NETTLEVINE_BLIGHT.characteristics.subtypes


def test_mop_tag_symbiote_bond_is_aura():
    from src.cards.custom.man_of_pider import SYMBIOTE_BOND
    assert "Aura" in SYMBIOTE_BOND.characteristics.subtypes


def test_mop_tag_genetic_mutation_is_aura():
    from src.cards.custom.man_of_pider import GENETIC_MUTATION
    assert "Aura" in GENETIC_MUTATION.characteristics.subtypes


def test_mop_tag_web_cocoon_is_aura():
    from src.cards.custom.man_of_pider import WEB_COCOON
    assert "Aura" in WEB_COCOON.characteristics.subtypes


def test_mha_tag_provisional_license_is_aura():
    from src.cards.custom.my_hero_academia import PROVISIONAL_LICENSE
    assert "Aura" in PROVISIONAL_LICENSE.characteristics.subtypes


def test_mha_tag_trigger_drug_is_aura():
    from src.cards.custom.my_hero_academia import TRIGGER_DRUG
    assert "Aura" in TRIGGER_DRUG.characteristics.subtypes


def test_mha_tag_one_for_all_is_aura():
    from src.cards.custom.my_hero_academia import ONE_FOR_ALL
    assert "Aura" in ONE_FOR_ALL.characteristics.subtypes


def test_mha_tag_full_cowling_aura_is_aura():
    from src.cards.custom.my_hero_academia import FULL_COWLING_AURA
    assert "Aura" in FULL_COWLING_AURA.characteristics.subtypes


def test_nrt_tag_curse_of_hatred_is_aura():
    from src.cards.custom.naruto import CURSE_OF_HATRED
    assert "Aura" in CURSE_OF_HATRED.characteristics.subtypes


def test_nrt_tag_nine_tails_cloak_is_aura():
    from src.cards.custom.naruto import NINE_TAILS_CLOAK
    assert "Aura" in NINE_TAILS_CLOAK.characteristics.subtypes


def test_nrt_tag_susanoo_is_aura():
    from src.cards.custom.naruto import SUSANOO
    assert "Aura" in SUSANOO.characteristics.subtypes


def test_pa_tag_avatar_destiny_is_aura():
    from src.cards.custom.penultimate_avatar import AVATAR_DESTINY
    assert "Aura" in AVATAR_DESTINY.characteristics.subtypes


def test_pa_tag_spirit_corruption_is_aura():
    from src.cards.custom.penultimate_avatar import SPIRIT_CORRUPTION
    assert "Aura" in SPIRIT_CORRUPTION.characteristics.subtypes


def test_pa_tag_wild_growth_is_aura():
    from src.cards.custom.penultimate_avatar import WILD_GROWTH
    assert "Aura" in WILD_GROWTH.characteristics.subtypes


def test_pok_tag_leech_seed_is_aura():
    from src.cards.custom.pokemon_horizons import LEECH_SEED
    assert "Aura" in LEECH_SEED.characteristics.subtypes


def test_pct_tag_regen_is_aura():
    from src.cards.custom.princess_catholicon import REGEN
    assert "Aura" in REGEN.characteristics.subtypes


def test_pct_tag_auto_life_is_aura():
    from src.cards.custom.princess_catholicon import AUTO_LIFE
    assert "Aura" in AUTO_LIFE.characteristics.subtypes


def test_pct_tag_poison_is_aura():
    from src.cards.custom.princess_catholicon import POISON
    assert "Aura" in POISON.characteristics.subtypes


def test_pct_tag_wild_growth_is_aura():
    from src.cards.custom.princess_catholicon import WILD_GROWTH
    assert "Aura" in WILD_GROWTH.characteristics.subtypes


def test_pct_tag_berserk_is_aura():
    from src.cards.custom.princess_catholicon import BERSERK
    assert "Aura" in BERSERK.characteristics.subtypes


def test_pct_tag_vanish_is_aura():
    from src.cards.custom.princess_catholicon import VANISH
    assert "Aura" in VANISH.characteristics.subtypes


def test_th_tag_temporal_roots_is_aura():
    from src.cards.custom.temporal_horizons import TEMPORAL_ROOTS
    assert "Aura" in TEMPORAL_ROOTS.characteristics.subtypes


# =============================================================================
# List B — Helper 5 wired triggers (assert ATTACH installs the trigger and
# the granted ability fires on the matching event)
# =============================================================================

def test_dms_blazing_rage_zaps_on_attack():
    from src.cards.custom.demon_slayer import BLAZING_RAGE
    game, p1, p2 = _new_game()
    aura = _put_card(game, p1, BLAZING_RAGE)
    creature = _put_card(game, p1, _plain_creature("Bearer"))
    _attach(game, aura, creature)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={
            'attacker_id': creature.id,
            'attacking_player': p1.id,
            'defending_player': p2.id,
        },
    ))
    assert _has_event(game, EventType.DAMAGE, target=p2.id, amount=1), (
        f"Blazing Rage should fire a 1-damage DAMAGE on defending player; "
        f"recent={[(e.type.name, e.payload) for e in game.state.event_log[-8:]]}"
    )


def test_dms_serpent_coils_taps_on_combat_dmg_to_creature():
    from src.cards.custom.demon_slayer import SERPENT_COILS
    game, p1, p2 = _new_game()
    aura = _put_card(game, p1, SERPENT_COILS)
    bearer = _put_card(game, p1, _plain_creature("Iguchi"))
    victim = _put_card(game, p2, _plain_creature("Demon", subtypes={"Demon"}))
    _attach(game, aura, bearer)
    _combat_dmg(game, bearer, victim.id, amount=3)
    assert _has_event(game, EventType.TAP, object_id=victim.id), (
        "Serpent Coils should fire a TAP on the victim creature"
    )


def test_mha_hero_license_gains_life_on_combat_dmg_to_player():
    from src.cards.custom.my_hero_academia import HERO_LICENSE
    game, p1, p2 = _new_game()
    aura = _put_card(game, p1, HERO_LICENSE)
    creature = _put_card(game, p1, _plain_creature("Hero"))
    _attach(game, aura, creature)
    _combat_dmg(game, creature, p2.id, amount=3)
    assert _has_event(game, EventType.LIFE_CHANGE, player=p1.id, amount=2), (
        "Hero License should gain controller 2 life on combat damage to player"
    )


def test_mha_explosive_power_zaps_on_attack():
    from src.cards.custom.my_hero_academia import EXPLOSIVE_POWER
    game, p1, p2 = _new_game()
    aura = _put_card(game, p1, EXPLOSIVE_POWER)
    creature = _put_card(game, p1, _plain_creature("Bakugo"))
    _attach(game, aura, creature)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={
            'attacker_id': creature.id,
            'attacking_player': p1.id,
            'defending_player': p2.id,
        },
    ))
    assert _has_event(game, EventType.DAMAGE, target=p2.id, amount=1), (
        "Explosive Power should fire a 1-damage DAMAGE on defending player"
    )


def test_lwn_morcants_eyes_draws_on_combat_dmg_to_player():
    from src.cards.custom.lorwyn_custom import MORCANTS_EYES
    game, p1, p2 = _new_game()
    aura = _put_card(game, p1, MORCANTS_EYES)
    creature = _put_card(game, p1, _plain_creature("Bearer"))
    _attach(game, aura, creature)
    _combat_dmg(game, creature, p2.id, amount=2)
    assert _has_event(game, EventType.DRAW, player=p1.id, amount=1), (
        "Morcant's Eyes should fire a DRAW for the controller on combat damage to player"
    )


def test_pa_dark_spirits_blessing_drains_on_enchanted_dies():
    from src.cards.custom.penultimate_avatar import DARK_SPIRITS_BLESSING
    game, p1, p2 = _new_game()
    aura = _put_card(game, p1, DARK_SPIRITS_BLESSING)
    bearer = _put_card(game, p1, _plain_creature("Cursed"))
    _attach(game, aura, bearer)
    # Simulate the enchanted creature dying.
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': bearer.id, 'reason': 'test_destroy'},
        source=bearer.id,
    ))
    assert _has_event(game, EventType.LIFE_CHANGE, player=p2.id, amount=-2), (
        "Dark Spirit's Blessing should drain 2 life from each opponent when the "
        "enchanted creature dies"
    )


# =============================================================================
# Test runner
# =============================================================================

def _collect_tests():
    g = globals()
    return [(name, fn) for name, fn in sorted(g.items()) if name.startswith("test_") and callable(fn)]


def main():
    tests = _collect_tests()
    passed = 0
    failed = []
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            failed.append((name, str(e)))
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
    width = 70
    print("=" * width)
    if failed:
        for name, err in failed:
            print(f"FAIL  {name}\n      {err}")
        print("=" * width)
    print(f"Total: {passed}/{len(tests)} passed")
    print("=" * width)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
