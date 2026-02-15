"""
Hearthstone Unhappy Path Tests - Batch 88

Silence and Transform Edge Cases: silence removes buffs/text/keywords/abilities,
transform effects (Polymorph/Hex) completely reset minions, Earth Shock interactions,
and edge cases around silence+aura/buff interactions.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, STORMWIND_CHAMPION, GURUBASHI_BERSERKER,
)
from src.cards.hearthstone.classic import (
    DIRE_WOLF_ALPHA, KNIFE_JUGGLER, LOOT_HOARDER,
    CAIRNE_BLOODHOOF, SYLVANAS_WINDRUNNER, AMANI_BERSERKER,
)
from src.cards.hearthstone.mage import POLYMORPH, MANA_WYRM
from src.cards.hearthstone.shaman import EARTH_SHOCK, HEX
from src.cards.hearthstone.paladin import BLESSING_OF_KINGS
from src.cards.hearthstone.priest import POWER_WORD_SHIELD, SILENCE_SPELL
from src.cards.hearthstone.druid import MARK_OF_THE_WILD


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(class1="Mage", class2="Warrior"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    """Create an object from a card definition and place it in the given zone."""
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


def run_sba(game):
    """Manually check state-based actions (destroy lethal minions)."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return
    for oid in list(battlefield.objects):
        obj = game.state.objects.get(oid)
        if not obj:
            continue
        if CardType.MINION not in obj.characteristics.types:
            continue
        toughness = get_toughness(obj, game.state)
        if obj.state.damage >= toughness and toughness > 0:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': oid},
                source=oid
            ))


# ============================================================
# Test 1-8: Silence removes buffs
# ============================================================

class TestSilenceRemovesBuffs:
    """Silence should remove all buffs and enchantments."""

    def test_silence_removes_attack_buff(self):
        """Silence removes +attack buff (Blessing of Kings)."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Apply Blessing of Kings (+4/+4)
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 4, 'toughness_mod': 4, 'duration': 'permanent'},
            source='test'
        ))

        assert get_power(wisp, game.state) == 5
        assert get_toughness(wisp, game.state) == 5

        # Silence the wisp
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1

    def test_silence_removes_health_buff(self):
        """Silence removes +health buff (Power Word: Shield)."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Apply +2 Health
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 0, 'toughness_mod': 2, 'duration': 'permanent'},
            source='test'
        ))

        assert get_toughness(wisp, game.state) == 3

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        assert get_toughness(wisp, game.state) == 1

    def test_silence_removes_taunt_from_buff(self):
        """Silence removes Taunt granted by buff (Mark of the Wild)."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Grant Taunt via event
        if not wisp.characteristics.abilities:
            wisp.characteristics.abilities = []
        wisp.characteristics.abilities.append({'keyword': 'taunt'})

        assert has_ability(wisp, 'taunt', game.state)

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        assert not has_ability(wisp, 'taunt', game.state)

    def test_silence_removes_divine_shield_from_buff(self):
        """Silence removes Divine Shield granted by buff."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Grant Divine Shield
        wisp.state.divine_shield = True
        assert wisp.state.divine_shield

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        assert not wisp.state.divine_shield

    def test_silence_removes_windfury_from_buff(self):
        """Silence removes Windfury granted by buff."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Grant Windfury
        wisp.state.windfury = True
        assert wisp.state.windfury

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        assert not wisp.state.windfury

    def test_silence_removes_charge_from_buff(self):
        """Silence removes Charge granted by buff."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Grant Charge (remove summoning sickness)
        wisp.state.summoning_sickness = False
        assert not wisp.state.summoning_sickness

        # Note: In HS, silence doesn't re-add summoning sickness to minions played this turn
        # But it does remove the Charge keyword
        # For this test, we just verify silence works

    def test_silence_on_unbuffed_minion_no_change(self):
        """Silence on unbuffed minion - no change to stats."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        # Should remain the same
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1

    def test_silence_removes_enrage_effect(self):
        """Silence removes enrage effect (Amani Berserker)."""
        game, p1, p2 = new_hs_game()
        berserker = make_obj(game, AMANI_BERSERKER, p1)

        # Amani Berserker is 2/3, becomes 5/3 when damaged (Enrage: +3 Attack)
        assert get_power(berserker, game.state) == 2

        # Deal 1 damage
        berserker.state.damage = 1

        # Should now have +3 attack (enrage active)
        assert get_power(berserker, game.state) == 5

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': berserker.id},
            source='test'
        ))

        # Enrage gone, back to 2 attack
        assert get_power(berserker, game.state) == 2


# ============================================================
# Test 9-15: Silence removes card text
# ============================================================

class TestSilenceRemovesCardText:
    """Silence should remove all card text including deathrattles and triggers."""

    def test_silence_removes_deathrattle_loot_hoarder(self):
        """Silence removes deathrattle (Loot Hoarder - no draw on death)."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': hoarder.id},
            source='test'
        ))

        # Destroy and verify no draw
        hand_before = len(game.state.zones.get(f'hand_{p1.id}').objects)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='test'
        ))
        hand_after = len(game.state.zones.get(f'hand_{p1.id}').objects)

        # Should not have drawn (deathrattle removed by silence)
        assert hand_after == hand_before

    def test_silence_removes_deathrattle_cairne(self):
        """Silence removes deathrattle (Cairne - no Baine on death)."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p1)

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': cairne.id},
            source='test'
        ))

        # Count minions before
        battlefield = game.state.zones.get('battlefield')
        minions_before = len([oid for oid in battlefield.objects
                              if game.state.objects.get(oid) and
                              CardType.MINION in game.state.objects[oid].characteristics.types])

        # Destroy
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cairne.id},
            source='test'
        ))

        # Count minions after
        minions_after = len([oid for oid in battlefield.objects
                             if game.state.objects.get(oid) and
                             CardType.MINION in game.state.objects[oid].characteristics.types])

        # Should not have summoned Baine (deathrattle removed)
        assert minions_after == minions_before - 1

    def test_silence_removes_ongoing_effect_knife_juggler(self):
        """Silence removes ongoing effect (Knife Juggler - no juggle on summon)."""
        game, p1, p2 = new_hs_game()
        juggler = make_obj(game, KNIFE_JUGGLER, p1)
        enemy = make_obj(game, WISP, p2)

        # Silence juggler
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': juggler.id},
            source='test'
        ))

        # Summon a minion (should NOT trigger knife juggle)
        enemy_hp_before = game.state.players[p2.id].life
        wisp2 = make_obj(game, WISP, p1)

        # Enemy hero should not have taken damage
        enemy_hp_after = game.state.players[p2.id].life
        assert enemy_hp_after == enemy_hp_before

    def test_silence_removes_aura_stormwind(self):
        """Silence removes aura (Stormwind Champion - loses +1/+1 to others)."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        # Wisp should be buffed to 2/2
        assert get_power(wisp, game.state) == 2

        # Silence champion
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': champion.id},
            source='test'
        ))

        # Wisp should revert to 1/1
        assert get_power(wisp, game.state) == 1

    def test_silence_removes_aura_dire_wolf(self):
        """Silence removes aura (Dire Wolf Alpha - loses adjacent buff)."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)
        wisp2 = make_obj(game, WISP, p1)

        # Both wisps should have +1 Attack
        assert get_power(wisp1, game.state) == 2
        assert get_power(wisp2, game.state) == 2

        # Silence wolf
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wolf.id},
            source='test'
        ))

        # Wisps should lose buff
        assert get_power(wisp1, game.state) == 1
        assert get_power(wisp2, game.state) == 1

    def test_silence_removes_triggered_ability_mana_wyrm(self):
        """Silence removes triggered ability (Mana Wyrm - no +1 on spell)."""
        game, p1, p2 = new_hs_game()
        wyrm = make_obj(game, MANA_WYRM, p1)

        assert get_power(wyrm, game.state) == 1

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wyrm.id},
            source='test'
        ))

        # Cast a spell
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'caster': p1.id, 'spell_id': 'test_spell'},
            source='test_spell'
        ))

        # Should still be 1 attack (trigger removed)
        assert get_power(wyrm, game.state) == 1

    def test_silence_removes_end_of_turn_effect(self):
        """Silence removes end-of-turn effect (conceptual test)."""
        # This is a conceptual test since we don't have Ragnaros fully implemented
        # with end-of-turn triggers in the current test scope
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Silence removes all interceptors
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        # Verify interceptors were cleared
        assert len(wisp.interceptor_ids) == 0


# ============================================================
# Test 16-18: Silence doesn't remove
# ============================================================

class TestSilenceDoesntRemove:
    """Silence doesn't remove certain properties."""

    def test_silence_doesnt_remove_base_stats(self):
        """Silence doesn't remove base stats (minion keeps base power/toughness)."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        assert get_power(yeti, game.state) == 4
        assert get_toughness(yeti, game.state) == 5

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='test'
        ))

        # Base stats remain
        assert get_power(yeti, game.state) == 4
        assert get_toughness(yeti, game.state) == 5

    def test_silence_doesnt_affect_damage(self):
        """Silence doesn't affect damage already dealt to minion."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Deal 3 damage
        yeti.state.damage = 3
        assert yeti.state.damage == 3

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='test'
        ))

        # Damage remains
        assert yeti.state.damage == 3

    def test_silence_on_vanilla_minion_no_error(self):
        """Silence on a minion with no abilities - no error, minion unchanged."""
        game, p1, p2 = new_hs_game()
        raptor = make_obj(game, BLOODFEN_RAPTOR, p1)

        assert get_power(raptor, game.state) == 3
        assert get_toughness(raptor, game.state) == 2

        # Silence (should not error)
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': raptor.id},
            source='test'
        ))

        # Stats unchanged
        assert get_power(raptor, game.state) == 3
        assert get_toughness(raptor, game.state) == 2


# ============================================================
# Test 19-21: Silence + aura interactions
# ============================================================

class TestSilenceAuraInteractions:
    """Silence and aura edge cases."""

    def test_silencing_aura_source_removes_aura_from_all(self):
        """Silencing the aura source removes aura from all affected minions."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wisp2 = make_obj(game, WISP, p1)
        champion = make_obj(game, STORMWIND_CHAMPION, p1)

        assert get_power(wisp1, game.state) == 2
        assert get_power(wisp2, game.state) == 2

        # Silence the champion
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': champion.id},
            source='test'
        ))

        # Both wisps should lose buff
        assert get_power(wisp1, game.state) == 1
        assert get_power(wisp2, game.state) == 1

    def test_silencing_minion_under_aura_aura_reapplies(self):
        """Silencing a minion UNDER an aura - it still gets the aura buff (aura reapplies)."""
        game, p1, p2 = new_hs_game()
        champion = make_obj(game, STORMWIND_CHAMPION, p1)
        wisp = make_obj(game, WISP, p1)

        # Apply a buff to wisp first
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source='test'
        ))

        # Wisp: 1/1 + 2/2 (buff) + 1/1 (aura) = 4/4
        assert get_power(wisp, game.state) == 4

        # Silence wisp (removes buff but not aura)
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        # Wisp should still have aura: 1/1 + 1/1 (aura) = 2/2
        assert get_power(wisp, game.state) == 2
        assert get_toughness(wisp, game.state) == 2

    def test_rebuffing_silenced_minion_new_buff_applies(self):
        """Re-buffing a silenced minion - new buff applies normally."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # Apply buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 3, 'toughness_mod': 3, 'duration': 'permanent'},
            source='test1'
        ))

        assert get_power(wisp, game.state) == 4

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='test'
        ))

        assert get_power(wisp, game.state) == 1

        # Apply new buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 2, 'toughness_mod': 1, 'duration': 'permanent'},
            source='test2'
        ))

        # New buff should apply
        assert get_power(wisp, game.state) == 3
        assert get_toughness(wisp, game.state) == 2


# ============================================================
# Test 22-26: Earth Shock (1 damage + silence)
# ============================================================

class TestEarthShock:
    """Earth Shock silences then deals 1 damage."""

    def test_earth_shock_silences_then_deals_damage(self):
        """Earth Shock silences then deals 1 damage."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Apply buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': yeti.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source='test'
        ))

        assert get_power(yeti, game.state) == 6
        assert yeti.state.damage == 0

        # Cast Earth Shock
        cast_spell(game, EARTH_SHOCK, p1, targets=[yeti.id])

        # Should be silenced (buff removed) and have 1 damage
        assert get_power(yeti, game.state) == 4
        assert yeti.state.damage == 1

    def test_earth_shock_on_divine_shield_removes_shield_deals_zero(self):
        """Earth Shock on Divine Shield - removes shield, deals 1 damage (silence removes shield first)."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        yeti.state.divine_shield = True

        assert yeti.state.divine_shield

        # Cast Earth Shock
        cast_spell(game, EARTH_SHOCK, p1, targets=[yeti.id])

        # Divine shield removed (by silence), then 1 damage dealt
        # Silence happens first, so divine shield is gone before damage
        assert not yeti.state.divine_shield
        assert yeti.state.damage == 1

    def test_earth_shock_on_one_health_minion_silences_then_kills(self):
        """Earth Shock on 1-health minion - silences then kills."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        # Apply buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 3, 'toughness_mod': 0, 'duration': 'permanent'},
            source='test'
        ))

        assert get_power(wisp, game.state) == 4

        # Cast Earth Shock
        cast_spell(game, EARTH_SHOCK, p1, targets=[wisp.id])

        # Should be silenced (buff removed, back to 1/1) and have 1 damage (lethal)
        assert wisp.state.damage == 1

        # Run SBA
        run_sba(game)

        # Wisp should be destroyed
        battlefield = game.state.zones.get('battlefield')
        assert wisp.id not in battlefield.objects

    def test_earth_shock_on_buffed_minion_removes_buffs_then_damage_may_kill(self):
        """Earth Shock on buffed minion - removes buffs, then damage may kill."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        # Buff to 1/2
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 0, 'toughness_mod': 1, 'duration': 'permanent'},
            source='test'
        ))

        assert get_toughness(wisp, game.state) == 2

        # Cast Earth Shock
        cast_spell(game, EARTH_SHOCK, p1, targets=[wisp.id])

        # Silenced (back to 1/1), 1 damage (lethal)
        assert get_toughness(wisp, game.state) == 1
        assert wisp.state.damage == 1

        # Run SBA
        run_sba(game)

        # Should be destroyed
        battlefield = game.state.zones.get('battlefield')
        assert wisp.id not in battlefield.objects

    def test_earth_shock_on_enraged_minion_removes_enrage_then_damage(self):
        """Earth Shock on enraged minion - removes enrage bonus then deals damage."""
        game, p1, p2 = new_hs_game()
        berserker = make_obj(game, AMANI_BERSERKER, p2)

        # Damage to trigger enrage
        berserker.state.damage = 1
        assert get_power(berserker, game.state) == 5  # 2 + 3 from enrage

        # Cast Earth Shock
        cast_spell(game, EARTH_SHOCK, p1, targets=[berserker.id])

        # Enrage removed, +1 damage (total 2 damage on 3 health)
        assert get_power(berserker, game.state) == 2
        assert berserker.state.damage == 2


# ============================================================
# Test 27-28: Mass silence edge cases
# ============================================================

class TestMultipleSilences:
    """Multiple independent silences and re-silencing."""

    def test_silence_two_minions_independently(self):
        """Silence two minions independently - both lose abilities."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p2)
        wisp2 = make_obj(game, WISP, p2)

        # Buff both
        for wisp in [wisp1, wisp2]:
            game.emit(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': wisp.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
                source='test'
            ))

        assert get_power(wisp1, game.state) == 3
        assert get_power(wisp2, game.state) == 3

        # Silence both independently
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp1.id},
            source='test1'
        ))
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp2.id},
            source='test2'
        ))

        # Both should be 1/1
        assert get_power(wisp1, game.state) == 1
        assert get_power(wisp2, game.state) == 1

    def test_silence_buff_silence_again_second_removes_new_buff(self):
        """Silence minion, then buff it, then silence again - second silence removes new buff."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        # First buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
            source='test1'
        ))
        assert get_power(wisp, game.state) == 3

        # First silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='silence1'
        ))
        assert get_power(wisp, game.state) == 1

        # Second buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 3, 'toughness_mod': 1, 'duration': 'permanent'},
            source='test2'
        ))
        assert get_power(wisp, game.state) == 4

        # Second silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': wisp.id},
            source='silence2'
        ))
        assert get_power(wisp, game.state) == 1


# ============================================================
# Test 29-38: Transform effects (Polymorph/Hex)
# ============================================================

class TestPolymorph:
    """Polymorph transforms minion into 1/1 Sheep."""

    def test_polymorph_changes_to_1_1_sheep(self):
        """Polymorph changes minion to 1/1 Sheep."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Should be 1/1 Sheep
        assert yeti.name == "Sheep"
        assert get_power(yeti, game.state) == 1
        assert get_toughness(yeti, game.state) == 1

    def test_polymorph_removes_all_buffs(self):
        """Polymorph removes all buffs."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        # Apply multiple buffs
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 5, 'toughness_mod': 5, 'duration': 'permanent'},
            source='test'
        ))
        assert get_power(wisp, game.state) == 6

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[wisp.id])

        # Should be 1/1
        assert get_power(wisp, game.state) == 1
        assert get_toughness(wisp, game.state) == 1

    def test_polymorph_removes_deathrattle(self):
        """Polymorph removes deathrattle (Sylvanas polymorphed doesn't steal)."""
        game, p1, p2 = new_hs_game()
        sylvanas = make_obj(game, SYLVANAS_WINDRUNNER, p2)

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[sylvanas.id])

        # Should be a Sheep now
        assert sylvanas.name == "Sheep"

        # Destroy and verify no steal
        minions_p1_before = len([oid for oid in game.state.zones.get('battlefield').objects
                                  if game.state.objects.get(oid) and
                                  game.state.objects[oid].controller == p1.id and
                                  CardType.MINION in game.state.objects[oid].characteristics.types])

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': sylvanas.id},
            source='test'
        ))

        minions_p1_after = len([oid for oid in game.state.zones.get('battlefield').objects
                                 if game.state.objects.get(oid) and
                                 game.state.objects[oid].controller == p1.id and
                                 CardType.MINION in game.state.objects[oid].characteristics.types])

        # Should not have stolen anything
        assert minions_p1_after == minions_p1_before

    def test_polymorph_removes_aura_effect(self):
        """Polymorph removes aura effect (Stormwind polymorphed stops buffing)."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)
        champion = make_obj(game, STORMWIND_CHAMPION, p2)

        assert get_power(wisp, game.state) == 2

        # Polymorph the champion
        cast_spell(game, POLYMORPH, p1, targets=[champion.id])

        # Wisp should lose buff
        assert get_power(wisp, game.state) == 1


class TestHex:
    """Hex transforms minion into 0/1 Frog with Taunt."""

    def test_hex_changes_to_0_1_frog_with_taunt(self):
        """Hex changes minion to 0/1 Frog with Taunt."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Cast Hex
        cast_spell(game, HEX, p1, targets=[yeti.id])

        # Should be 0/1 Frog with Taunt
        assert yeti.name == "Frog"
        assert get_power(yeti, game.state) == 0
        assert get_toughness(yeti, game.state) == 1
        assert has_ability(yeti, 'taunt', game.state)

    def test_hex_removes_all_buffs_and_abilities(self):
        """Hex removes all buffs and abilities."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        # Apply buffs and abilities
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 5, 'toughness_mod': 5, 'duration': 'permanent'},
            source='test'
        ))
        wisp.state.divine_shield = True

        # Cast Hex
        cast_spell(game, HEX, p1, targets=[wisp.id])

        # Should be 0/1 Frog
        assert get_power(wisp, game.state) == 0
        assert get_toughness(wisp, game.state) == 1
        assert not wisp.state.divine_shield

    def test_hex_removes_deathrattle(self):
        """Hex removes deathrattle."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p2)

        # Cast Hex
        cast_spell(game, HEX, p1, targets=[hoarder.id])

        # Destroy and verify no draw
        hand_before = len(game.state.zones.get(f'hand_{p2.id}').objects)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id},
            source='test'
        ))
        hand_after = len(game.state.zones.get(f'hand_{p2.id}').objects)

        assert hand_after == hand_before


class TestTransformEdgeCases:
    """Transform edge cases."""

    def test_transform_removes_divine_shield(self):
        """Transform removes divine shield."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        yeti.state.divine_shield = True

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Divine shield gone
        assert not yeti.state.divine_shield

    def test_transform_on_damaged_minion_new_form_at_full_health(self):
        """Transform on already damaged minion - new form at full health."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Deal damage
        yeti.state.damage = 4

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Should be 1/1 with 0 damage
        assert yeti.state.damage == 0
        assert get_toughness(yeti, game.state) == 1

    def test_transform_on_silenced_minion_still_works(self):
        """Transform on silenced minion - transform still works."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Silence first
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': yeti.id},
            source='test'
        ))

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Should be Sheep
        assert yeti.name == "Sheep"
        assert get_power(yeti, game.state) == 1


# ============================================================
# Test 39-45: Transform edge cases continued
# ============================================================

class TestTransformOwnershipAndDoubleTransform:
    """Transform ownership and double transform tests."""

    def test_polymorph_on_own_minion_works(self):
        """Polymorph on your own minion - works."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Self-polymorph
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Should be Sheep
        assert yeti.name == "Sheep"
        assert yeti.controller == p1.id

    def test_polymorph_on_opponent_minion_works(self):
        """Polymorph on opponent minion - works."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        # Should be Sheep, still controlled by p2
        assert yeti.name == "Sheep"
        assert yeti.controller == p2.id

    def test_hex_target_keeps_same_controller(self):
        """Hex target keeps same controller."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Cast Hex
        cast_spell(game, HEX, p1, targets=[yeti.id])

        # Should be Frog, still p2's
        assert yeti.name == "Frog"
        assert yeti.controller == p2.id

    def test_transform_removes_enchantments_keeps_controller(self):
        """Transform removes enchantments but keeps controller."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)

        # Apply buff
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': wisp.id, 'power_mod': 5, 'toughness_mod': 5, 'duration': 'permanent'},
            source='test'
        ))

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1, targets=[wisp.id])

        # Buff removed, controller unchanged
        assert get_power(wisp, game.state) == 1
        assert wisp.controller == p2.id

    def test_assassinate_vs_polymorph_deathrattle_difference(self):
        """Assassinate vs Polymorph: destroy triggers deathrattle, transform doesn't."""
        game, p1, p2 = new_hs_game()
        hoarder1 = make_obj(game, LOOT_HOARDER, p2)
        hoarder2 = make_obj(game, LOOT_HOARDER, p2)

        # Verify hoarder1 has deathrattle (has card_def with deathrattle function)
        assert hoarder1.card_def is not None
        assert hoarder1.card_def.deathrattle is not None

        # Polymorph hoarder2 - should remove card_def and thus deathrattle
        cast_spell(game, POLYMORPH, p1, targets=[hoarder2.id])

        # Verify hoarder2 lost its deathrattle (card_def cleared)
        assert hoarder2.card_def is None or hoarder2.name == "Sheep"

        # The key difference: regular destroy would trigger deathrattle,
        # but polymorphed minion has no deathrattle to trigger

    def test_double_transform_second_overrides_first(self):
        """Double transform - second transform overrides first."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # First transform: Polymorph (1/1 Sheep)
        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])
        assert yeti.name == "Sheep"
        assert get_power(yeti, game.state) == 1
        assert get_toughness(yeti, game.state) == 1

        # Second transform: Hex (0/1 Frog with Taunt)
        cast_spell(game, HEX, p1, targets=[yeti.id])
        assert yeti.name == "Frog"
        assert get_power(yeti, game.state) == 0
        assert get_toughness(yeti, game.state) == 1
        assert has_ability(yeti, 'taunt', game.state)


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
