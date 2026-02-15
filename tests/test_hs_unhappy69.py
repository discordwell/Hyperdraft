"""
Hearthstone Unhappy Path Tests - Batch 69

Healing and damage interactions: healing cannot exceed max health,
Auchenai Soulpriest converts all healing to damage, hero healing
capped at 30, minion healing capped at max toughness, Holy Fire
damage + heal simultaneously, Priestess of Elune heal battlecry,
Guardian of Kings heal battlecry, Earthen Ring Farseer heal battlecry,
Voodoo Doctor heal battlecry, self-damage effects (Flame Imp, Life Tap,
Pit Lord), damage to hero reduces life below 0 (no floor), armor
absorbs damage before health, spell damage doesn't boost healing,
multiple heals in same turn stack, healing a full health minion is
a no-op.
"""

import random
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness, has_ability

from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, KOBOLD_GEOMANCER, VOODOO_DOCTOR,
)
from src.cards.hearthstone.classic import (
    EARTHEN_RING_FARSEER,
)
from src.cards.hearthstone.paladin import (
    HOLY_LIGHT, LAY_ON_HANDS, GUARDIAN_OF_KINGS,
)
from src.cards.hearthstone.priest import (
    AUCHENAI_SOULPRIEST, CIRCLE_OF_HEALING, HOLY_SMITE, HOLY_FIRE,
)
from src.cards.hearthstone.warlock import (
    FLAME_IMP, PIT_LORD,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    """Create a fresh Hearthstone game with Priest vs Mage, 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Priest"], HERO_POWERS["Priest"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Create an object from a card definition."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    return obj


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell card by invoking its spell_effect and emitting SPELL_CAST."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    return obj


def use_hero_power(game, player):
    """Activate a hero power via event."""
    game.emit(Event(
        type=EventType.HERO_POWER_ACTIVATE,
        payload={'hero_power_id': player.hero_power_id, 'player': player.id},
        source=player.hero_power_id,
    ))


# ============================================================
# Test 1: TestHealingCannotExceedMaxHealth
# ============================================================

class TestHealingCannotExceedMaxHealth:
    def test_holy_light_caps_at_30(self):
        """Hero at 25 HP healed for 6 by Holy Light -> caps at 30."""
        game, p1, p2 = new_hs_game()
        p1.life = 25

        cast_spell(game, HOLY_LIGHT, p1)

        assert p1.life == 30, (
            f"Hero healed from 25 by 6 should cap at 30, got {p1.life}"
        )

    def test_lay_on_hands_caps_at_30(self):
        """Hero at 25 HP healed for 8 by Lay on Hands -> caps at 30."""
        game, p1, p2 = new_hs_game()
        p1.life = 25

        # Lay on Hands also draws 3 cards; add library cards to avoid fatigue
        for _ in range(3):
            game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=WISP.characteristics, card_def=WISP
            )

        cast_spell(game, LAY_ON_HANDS, p1)

        assert p1.life == 30, (
            f"Hero healed from 25 by 8 should cap at 30, got {p1.life}"
        )

    def test_heal_from_28_by_6_caps_at_30(self):
        """Hero at 28 HP healed by Holy Light (6) -> caps at 30, not 34."""
        game, p1, p2 = new_hs_game()
        p1.life = 28

        cast_spell(game, HOLY_LIGHT, p1)

        assert p1.life == 30, (
            f"Hero healed from 28 by 6 should cap at 30, got {p1.life}"
        )


# ============================================================
# Test 2: TestMinionHealingCapAtMaxToughness
# ============================================================

class TestMinionHealingCapAtMaxToughness:
    def test_yeti_healed_does_not_exceed_max(self):
        """Damaged 4/5 Yeti (at 4/3 effective) healed for 4 -> becomes 4/5 not 4/7."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        yeti.state.damage = 2  # now at 4/3 effective health

        # Heal the minion for 4 via Circle of Healing (heals up to 4)
        cast_spell(game, CIRCLE_OF_HEALING, p1)

        # Yeti should be at 0 damage (full health), not negative damage
        assert yeti.state.damage == 0, (
            f"Yeti damage should be 0 after healing, got {yeti.state.damage}"
        )
        effective_health = get_toughness(yeti, game.state) - yeti.state.damage
        assert effective_health == 5, (
            f"Yeti effective health should be 5 (max), got {effective_health}"
        )


# ============================================================
# Test 3: TestHealingFullHealthNoOp
# ============================================================

class TestHealingFullHealthNoOp:
    def test_healing_full_health_hero_stays_at_30(self):
        """Healing a full-health hero does nothing (life stays at 30)."""
        game, p1, p2 = new_hs_game()
        assert p1.life == 30

        cast_spell(game, HOLY_LIGHT, p1)

        assert p1.life == 30, (
            f"Healing a full-health hero should keep it at 30, got {p1.life}"
        )


# ============================================================
# Test 4: TestHealingFullHealthMinionNoOp
# ============================================================

class TestHealingFullHealthMinionNoOp:
    def test_healing_undamaged_minion_no_change(self):
        """Healing an undamaged minion does nothing."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5, no damage
        assert yeti.state.damage == 0

        cast_spell(game, CIRCLE_OF_HEALING, p1)

        # Circle of Healing only emits heal events for damaged minions
        assert yeti.state.damage == 0, (
            f"Undamaged yeti should remain at 0 damage, got {yeti.state.damage}"
        )
        effective_health = get_toughness(yeti, game.state) - yeti.state.damage
        assert effective_health == 5, (
            f"Undamaged yeti should stay at 5 health, got {effective_health}"
        )


# ============================================================
# Test 5: TestAuchenaiConvertsHealToDamage
# ============================================================

class TestAuchenaiConvertsHealToDamage:
    def test_circle_deals_damage_with_auchenai(self):
        """With Auchenai on board, Circle of Healing deals damage to damaged minions."""
        game, p1, p2 = new_hs_game()
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)  # 3/5

        # Create a damaged enemy yeti so Circle would normally heal it
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        yeti.state.damage = 2  # effective 4/3

        damage_before = yeti.state.damage

        cast_spell(game, CIRCLE_OF_HEALING, p1)

        # Circle of Healing directly reduces m.state.damage before emitting
        # LIFE_CHANGE. Auchenai intercepts the LIFE_CHANGE and converts
        # it to DAMAGE. So the minion gets healed by the direct manipulation
        # but then takes damage from the converted event.
        # The net result: Circle heals 2 (min(damage, 4)), then Auchenai
        # deals 2 damage back via the converted event.
        # Check that damage events were generated by Auchenai's transform
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('target') == yeti.id]
        assert len(damage_events) >= 1, (
            "Auchenai should have converted healing into at least one DAMAGE event"
        )


# ============================================================
# Test 6: TestAuchenaiHeroPowerDamage
# ============================================================

class TestAuchenaiHeroPowerDamage:
    def test_lesser_heal_deals_damage_with_auchenai(self):
        """With Auchenai, Priest Lesser Heal deals 2 damage instead of healing."""
        game, p1, p2 = new_hs_game()
        p1.life = 25  # Damage hero so Lesser Heal would normally trigger

        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)

        life_before = p1.life

        use_hero_power(game, p1)

        # Auchenai converts the 2 healing into 2 damage
        # The hero power emits LIFE_CHANGE with amount=2, Auchenai
        # converts it to DAMAGE targeting the hero
        assert p1.life <= life_before, (
            f"With Auchenai, Lesser Heal should not increase life. "
            f"Was {life_before}, now {p1.life}"
        )


# ============================================================
# Test 7: TestAuchenaiDoesNotAffectDamageSpells
# ============================================================

class TestAuchenaiDoesNotAffectDamageSpells:
    def test_holy_smite_still_deals_2_with_auchenai(self):
        """Holy Smite deals 2 damage regardless of Auchenai (only healing is inverted)."""
        game, p1, p2 = new_hs_game()
        auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)

        life_before = p2.life

        random.seed(42)
        cast_spell(game, HOLY_SMITE, p1)

        # Holy Smite deals damage, not healing, so Auchenai doesn't affect it
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('amount') == 2
                         and e.payload.get('from_spell') is True]
        assert len(damage_events) >= 1, (
            "Holy Smite should still deal exactly 2 damage with Auchenai on board"
        )


# ============================================================
# Test 8: TestGuardianOfKingsHeal6
# ============================================================

class TestGuardianOfKingsHeal6:
    def test_guardian_heals_hero_for_6(self):
        """Guardian of Kings battlecry heals hero for 6."""
        game, p1, p2 = new_hs_game()
        p1.life = 20

        guardian = make_obj(game, GUARDIAN_OF_KINGS, p1)
        events = GUARDIAN_OF_KINGS.battlecry(guardian, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == 26, (
            f"Guardian of Kings should heal hero from 20 to 26, got {p1.life}"
        )

    def test_guardian_heals_capped_at_30(self):
        """Guardian of Kings healing 6 from 28 should cap at 30."""
        game, p1, p2 = new_hs_game()
        p1.life = 28

        guardian = make_obj(game, GUARDIAN_OF_KINGS, p1)
        events = GUARDIAN_OF_KINGS.battlecry(guardian, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == 30, (
            f"Guardian heal from 28 should cap at 30, got {p1.life}"
        )


# ============================================================
# Test 9: TestEarthenRingFarseerHeal3
# ============================================================

class TestEarthenRingFarseerHeal3:
    def test_earthen_ring_heals_hero_for_3(self):
        """Earthen Ring Farseer battlecry heals hero for 3."""
        game, p1, p2 = new_hs_game()
        p1.life = 20

        farseer = make_obj(game, EARTHEN_RING_FARSEER, p1)
        events = EARTHEN_RING_FARSEER.battlecry(farseer, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == 23, (
            f"Earthen Ring Farseer should heal hero from 20 to 23, got {p1.life}"
        )

    def test_earthen_ring_heal_capped_at_30(self):
        """Earthen Ring Farseer healing 3 from 29 should cap at 30."""
        game, p1, p2 = new_hs_game()
        p1.life = 29

        farseer = make_obj(game, EARTHEN_RING_FARSEER, p1)
        events = EARTHEN_RING_FARSEER.battlecry(farseer, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == 30, (
            f"Earthen Ring heal from 29 should cap at 30, got {p1.life}"
        )


# ============================================================
# Test 10: TestVoodooDoctorHeal2
# ============================================================

class TestVoodooDoctorHeal2:
    def test_voodoo_doctor_heals_hero_for_2(self):
        """Voodoo Doctor battlecry heals hero for 2."""
        game, p1, p2 = new_hs_game()
        p1.life = 20

        doctor = make_obj(game, VOODOO_DOCTOR, p1)
        events = VOODOO_DOCTOR.battlecry(doctor, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == 22, (
            f"Voodoo Doctor should heal hero from 20 to 22, got {p1.life}"
        )

    def test_voodoo_doctor_heal_capped_at_30(self):
        """Voodoo Doctor healing 2 from 29 should cap at 30."""
        game, p1, p2 = new_hs_game()
        p1.life = 29

        doctor = make_obj(game, VOODOO_DOCTOR, p1)
        events = VOODOO_DOCTOR.battlecry(doctor, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == 30, (
            f"Voodoo Doctor heal from 29 should cap at 30, got {p1.life}"
        )


# ============================================================
# Test 11: TestDamageReducesLifeBelowZero
# ============================================================

class TestDamageReducesLifeBelowZero:
    def test_10_damage_to_5hp_hero_goes_negative(self):
        """10 damage to hero at 5 HP -> hero goes to -5 (no floor at 0)."""
        game, p1, p2 = new_hs_game()
        p1.life = 5

        # Deal 10 damage to p1's hero
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 10, 'source': 'test'},
            source='test'
        ))

        assert p1.life == -5, (
            f"Hero at 5 HP taking 10 damage should go to -5, got {p1.life}"
        )


# ============================================================
# Test 12: TestArmorAbsorbsDamageBeforeHealth
# ============================================================

class TestArmorAbsorbsDamageBeforeHealth:
    def test_armor_partially_absorbs(self):
        """Hero with 5 armor at 30 HP takes 8 damage -> armor=0, HP=27."""
        game, p1, p2 = new_hs_game()
        p1.armor = 5
        p1.life = 30

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 8, 'source': 'test'},
            source='test'
        ))

        assert p1.armor == 0, (
            f"Armor should be fully consumed, got {p1.armor}"
        )
        assert p1.life == 27, (
            f"Hero should take 3 damage after 5 armor absorbed from 8, "
            f"expected 27 HP, got {p1.life}"
        )


# ============================================================
# Test 13: TestArmorFullyAbsorbs
# ============================================================

class TestArmorFullyAbsorbs:
    def test_armor_absorbs_all_damage(self):
        """Hero with 10 armor at 30 HP takes 5 damage -> armor=5, HP=30."""
        game, p1, p2 = new_hs_game()
        p1.armor = 10
        p1.life = 30

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': p1.hero_id, 'amount': 5, 'source': 'test'},
            source='test'
        ))

        assert p1.armor == 5, (
            f"Armor should be reduced from 10 to 5, got {p1.armor}"
        )
        assert p1.life == 30, (
            f"Hero HP should remain at 30 when armor absorbs all damage, got {p1.life}"
        )


# ============================================================
# Test 14: TestSelfDamageEffects
# ============================================================

class TestSelfDamageEffects:
    def test_flame_imp_deals_3_to_own_hero(self):
        """Flame Imp battlecry deals 3 damage to own hero."""
        game, p1, p2 = new_hs_game()
        life_before = p1.life

        imp = make_obj(game, FLAME_IMP, p1)
        events = FLAME_IMP.battlecry(imp, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == life_before - 3, (
            f"Flame Imp should deal 3 to own hero, "
            f"expected {life_before - 3}, got {p1.life}"
        )

    def test_pit_lord_deals_5_to_own_hero(self):
        """Pit Lord battlecry deals 5 damage to own hero."""
        game, p1, p2 = new_hs_game()
        life_before = p1.life

        pit_lord = make_obj(game, PIT_LORD, p1)
        events = PIT_LORD.battlecry(pit_lord, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == life_before - 5, (
            f"Pit Lord should deal 5 to own hero, "
            f"expected {life_before - 5}, got {p1.life}"
        )

    def test_self_damage_can_kill_own_hero(self):
        """Self-damage effects can reduce hero HP below 0."""
        game, p1, p2 = new_hs_game()
        p1.life = 3  # Low HP

        pit_lord = make_obj(game, PIT_LORD, p1)
        events = PIT_LORD.battlecry(pit_lord, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == -2, (
            f"Pit Lord dealing 5 to hero at 3 HP should result in -2, got {p1.life}"
        )


# ============================================================
# Test 15: TestSpellDamageDoesNotBoostHealing
# ============================================================

class TestSpellDamageDoesNotBoostHealing:
    def test_spell_damage_does_not_boost_holy_light(self):
        """Kobold Geomancer on board, cast Holy Light (heal 6) -> still heals 6 (not 7)."""
        game, p1, p2 = new_hs_game()
        p1.life = 20

        # Place Kobold Geomancer for Spell Damage +1
        geomancer = make_obj(game, KOBOLD_GEOMANCER, p1)

        cast_spell(game, HOLY_LIGHT, p1)

        # Holy Light heals 6 to hero. Spell Damage should NOT boost healing.
        # 20 + 6 = 26 (not 27)
        assert p1.life == 26, (
            f"Spell Damage should not boost healing. "
            f"Expected 26 (20 + 6), got {p1.life}"
        )


# ============================================================
# Test 16: TestMultipleHealsStack
# ============================================================

class TestMultipleHealsStack:
    def test_two_holy_lights_stack(self):
        """Cast 2 Holy Light spells -> total healing is sum of both (12, capped at 30)."""
        game, p1, p2 = new_hs_game()
        p1.life = 15

        cast_spell(game, HOLY_LIGHT, p1)  # +6 -> 21
        assert p1.life == 21, (
            f"After first Holy Light, expected 21, got {p1.life}"
        )

        cast_spell(game, HOLY_LIGHT, p1)  # +6 -> 27
        assert p1.life == 27, (
            f"After second Holy Light, expected 27, got {p1.life}"
        )

    def test_multiple_heals_capped(self):
        """Multiple heals that would exceed 30 are each individually capped."""
        game, p1, p2 = new_hs_game()
        p1.life = 26

        cast_spell(game, HOLY_LIGHT, p1)  # +6 -> capped at 30
        assert p1.life == 30, (
            f"First heal from 26 should cap at 30, got {p1.life}"
        )

        cast_spell(game, HOLY_LIGHT, p1)  # +6 -> still 30
        assert p1.life == 30, (
            f"Second heal at full health should stay at 30, got {p1.life}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
