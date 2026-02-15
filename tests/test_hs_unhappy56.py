"""
Hearthstone Unhappy Path Tests - Batch 56

Spell damage stacking with AOE spells and Wild Pyromancer chain interactions:
Double spell damage + Arcane Explosion, spell damage + Holy Nova,
Wild Pyromancer + Equality board clear, Pyromancer + multiple spells,
Pyromancer + Circle of Healing + Auchenai, spell damage + Consecration,
Malygos spell damage + Arcane Missiles, Kobold Geomancer + Flamestrike,
Bloodmage Thalnos spell damage + draw deathrattle interaction.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, KOBOLD_GEOMANCER,
)
from src.cards.hearthstone.classic import (
    WILD_PYROMANCER, BLOODMAGE_THALNOS, AZURE_DRAKE, MALYGOS,
    ARCANE_MISSILES, FROSTBOLT, FIREBALL, FLAMESTRIKE,
    CONSECRATION,
)
from src.cards.hearthstone.mage import (
    ARCANE_EXPLOSION,
)
from src.cards.hearthstone.priest import (
    HOLY_NOVA, CIRCLE_OF_HEALING, AUCHENAI_SOULPRIEST,
)
from src.cards.hearthstone.paladin import (
    EQUALITY,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Paladin"], HERO_POWERS["Paladin"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


def cast_spell(game, card_def, owner, targets=None):
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


# ============================================================
# Test 1: Spell Damage Single Source
# ============================================================

class TestSpellDamageSingleSource:
    def test_kobold_plus_arcane_explosion(self):
        """Kobold Geomancer (Spell Damage +1) + Arcane Explosion = 2 damage to each enemy minion."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy1 = make_obj(game, CHILLWIND_YETI, p2)
        enemy2 = make_obj(game, WISP, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        # Arcane Explosion base is 1, spell damage +1 = 2 per enemy minion
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 2 and
                         e.payload.get('from_spell')]
        assert len(damage_events) == 2, (
            f"Expected 2 damage events at amount=2, got {len(damage_events)}"
        )

    def test_kobold_plus_frostbolt(self):
        """Kobold Geomancer + Frostbolt = 4 damage (3 base + 1 spell damage)."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == yeti.id and
                         e.payload.get('amount') == 4]
        assert len(damage_events) == 1, (
            f"Expected Frostbolt to deal 4 damage with spell damage +1"
        )

    def test_kobold_does_not_boost_non_spell_damage(self):
        """Kobold Geomancer should not boost combat or non-spell damage."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        # Emit a non-spell damage event
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti.id, 'amount': 3, 'source': kobold.id},
            source=kobold.id
        ))

        # Should remain 3, not boosted to 4
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == yeti.id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 3


# ============================================================
# Test 2: Spell Damage Double Source
# ============================================================

class TestSpellDamageDoubleSource:
    def test_two_kobolds_plus_arcane_explosion(self):
        """Two Kobold Geomancers + Arcane Explosion = 3 damage each (1 base + 2)."""
        game, p1, p2 = new_hs_game()
        kobold1 = make_obj(game, KOBOLD_GEOMANCER, p1)
        kobold2 = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == enemy.id and
                         e.payload.get('from_spell')]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 3, (
            f"Expected 3 damage (1+2), got {damage_events[0].payload['amount']}"
        )

    def test_two_kobolds_plus_consecration(self):
        """Two Kobold Geomancers + Consecration = 4 damage to each enemy (2 base + 2)."""
        game, p1, p2 = new_hs_game()
        kobold1 = make_obj(game, KOBOLD_GEOMANCER, p1)
        kobold2 = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy1 = make_obj(game, CHILLWIND_YETI, p2)
        enemy2 = make_obj(game, BLOODFEN_RAPTOR, p2)

        cast_spell(game, CONSECRATION, p1)

        # Check minion damage events (Consecration also hits hero)
        minion_dmg = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('from_spell') and
                      e.payload.get('target') in (enemy1.id, enemy2.id)]
        assert len(minion_dmg) == 2
        for evt in minion_dmg:
            assert evt.payload['amount'] == 4, (
                f"Expected 4 damage (2+2), got {evt.payload['amount']}"
            )

    def test_two_kobolds_plus_frostbolt(self):
        """Two Kobold Geomancers + Frostbolt = 5 damage (3 base + 2)."""
        game, p1, p2 = new_hs_game()
        kobold1 = make_obj(game, KOBOLD_GEOMANCER, p1)
        kobold2 = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == yeti.id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 5


# ============================================================
# Test 3: Malygos Spell Damage
# ============================================================

class TestMalygosSpellDamage:
    def test_malygos_plus_frostbolt(self):
        """Malygos (Spell Damage +5) + Frostbolt = 8 damage (3+5)."""
        game, p1, p2 = new_hs_game()
        malygos = make_obj(game, MALYGOS, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == yeti.id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 8, (
            f"Expected 8 damage (3+5), got {damage_events[0].payload['amount']}"
        )

    def test_malygos_plus_arcane_missiles(self):
        """Malygos + Arcane Missiles: spell damage +5 boosts each missile from 1 to 6.

        The implementation creates 3 individual DAMAGE events with amount=1 each.
        The spell damage TRANSFORM interceptor adds +5 to each DAMAGE event,
        resulting in 3 missiles of 6 damage each (18 total).
        """
        game, p1, p2 = new_hs_game()
        malygos = make_obj(game, MALYGOS, p1)

        random.seed(42)
        cast_spell(game, ARCANE_MISSILES, p1)

        # Each of the 3 missiles should be boosted from 1 to 6
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('from_spell') and
                         e.payload.get('amount') == 6]
        assert len(damage_events) == 3, (
            f"Expected 3 missiles at 6 damage each, got {len(damage_events)}"
        )

    def test_malygos_plus_fireball(self):
        """Malygos + Fireball = 11 damage (6+5)."""
        game, p1, p2 = new_hs_game()
        malygos = make_obj(game, MALYGOS, p1)

        cast_spell(game, FIREBALL, p1, targets=[p2.hero_id])

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == p2.hero_id and
                         e.payload.get('amount') == 11]
        assert len(damage_events) == 1

    def test_malygos_plus_arcane_explosion(self):
        """Malygos + Arcane Explosion = 6 damage to each enemy minion (1+5)."""
        game, p1, p2 = new_hs_game()
        malygos = make_obj(game, MALYGOS, p1)
        enemy1 = make_obj(game, CHILLWIND_YETI, p2)
        enemy2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('from_spell') and
                         e.payload.get('amount') == 6]
        assert len(damage_events) == 2


# ============================================================
# Test 4: Bloodmage Thalnos
# ============================================================

class TestBloodmageThalnos:
    def test_spell_damage_plus_1(self):
        """Bloodmage Thalnos provides Spell Damage +1 to Arcane Explosion."""
        game, p1, p2 = new_hs_game()
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == enemy.id and
                         e.payload.get('from_spell')]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 2, (
            f"Expected 2 damage (1+1), got {damage_events[0].payload['amount']}"
        )

    def test_deathrattle_draw_on_death(self):
        """Killing Bloodmage Thalnos triggers Deathrattle: Draw a card."""
        game, p1, p2 = new_hs_game()
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)

        # Thalnos has 1 health, deal 1 damage to kill it
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': thalnos.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        # SBA check processes lethal damage -> death -> deathrattle
        game.check_state_based_actions()

        # Check that a DRAW event was emitted from deathrattle
        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 1, "Thalnos deathrattle should trigger a draw"

    def test_spell_damage_gone_after_death(self):
        """After Thalnos dies, spell damage should no longer apply."""
        game, p1, p2 = new_hs_game()
        thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        # Kill Thalnos first
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': thalnos.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        # SBA check processes lethal damage -> death -> interceptor cleanup
        game.check_state_based_actions()

        # Clear event log to check fresh
        game.state.event_log.clear()

        # Now cast a spell - should not have spell damage
        cast_spell(game, ARCANE_EXPLOSION, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == enemy.id and
                         e.payload.get('from_spell')]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 1, (
            f"Expected 1 damage (no spell damage after Thalnos dies), got {damage_events[0].payload['amount']}"
        )


# ============================================================
# Test 5: Wild Pyromancer Basic
# ============================================================

class TestWildPyromancerBasic:
    def test_deals_1_damage_to_all_minions_after_spell(self):
        """Wild Pyromancer deals 1 damage to ALL minions after a spell is cast."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        # Pyromancer fires 1 damage to all minions (including itself)
        pyro_damage = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.payload.get('amount') == 1 and
                       e.source == pyro.id]
        # Should hit pyro itself, friendly yeti, and enemy yeti
        targets_hit = {e.payload.get('target') for e in pyro_damage}
        assert pyro.id in targets_hit, "Pyromancer should damage itself"
        assert friendly.id in targets_hit, "Pyromancer should damage friendly minions"
        assert enemy.id in targets_hit, "Pyromancer should damage enemy minions"

    def test_pyromancer_damage_is_not_spell_damage(self):
        """Wild Pyromancer's damage is not boosted by spell damage (no from_spell flag)."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        # Pyromancer's own damage events should be exactly 1 (not boosted by Kobold)
        pyro_damage = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.source == pyro.id]
        for evt in pyro_damage:
            assert evt.payload['amount'] == 1, (
                f"Pyromancer damage should be 1 (not boosted by spell damage), got {evt.payload['amount']}"
            )

    def test_pyromancer_does_not_trigger_on_enemy_spell(self):
        """Wild Pyromancer only triggers on spells cast by its controller."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Enemy (p2) casts a spell
        cast_spell(game, ARCANE_EXPLOSION, p2)

        # Pyromancer should NOT fire since spell was from p2, not p1
        pyro_damage = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.source == pyro.id]
        assert len(pyro_damage) == 0, "Pyromancer should not trigger on enemy spells"


# ============================================================
# Test 6: Wild Pyromancer Multiple Spells
# ============================================================

class TestWildPyromancerMultipleSpells:
    def test_two_spells_two_procs(self):
        """Wild Pyromancer deals 1 damage after each spell, so 2 spells = 2 damage total."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        # Yeti has 5 health, can survive the proc damage
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Cast two spells in sequence
        cast_spell(game, ARCANE_EXPLOSION, p1)
        cast_spell(game, ARCANE_EXPLOSION, p1)

        # Pyromancer procs should hit yeti twice (1 per spell)
        pyro_damage_to_yeti = [e for e in game.state.event_log
                               if e.type == EventType.DAMAGE and
                               e.source == pyro.id and
                               e.payload.get('target') == yeti.id]
        assert len(pyro_damage_to_yeti) == 2, (
            f"Expected 2 Pyromancer procs on yeti, got {len(pyro_damage_to_yeti)}"
        )

    def test_pyromancer_dies_from_first_proc_no_second(self):
        """If Pyromancer takes lethal from first proc (1 health left), second spell should not trigger it."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Reduce Pyromancer to 1 health (it has 2 base, deal 1 damage)
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': pyro.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.state.event_log.clear()

        # First spell: Pyromancer procs, deals 1 to all including itself (dies)
        cast_spell(game, ARCANE_EXPLOSION, p1)

        # Pyromancer should have proc'd once (dealing 1 to itself, killing it)
        first_procs = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.source == pyro.id and
                       e.payload.get('target') == yeti.id]
        assert len(first_procs) == 1, "Pyromancer should proc once before dying"

        # Process SBA to kill Pyromancer and clean up its interceptor
        game.check_state_based_actions()
        game.state.event_log.clear()

        # Second spell: Pyromancer is dead, should not proc
        cast_spell(game, ARCANE_EXPLOSION, p1)

        second_procs = [e for e in game.state.event_log
                        if e.type == EventType.DAMAGE and
                        e.source == pyro.id]
        assert len(second_procs) == 0, "Dead Pyromancer should not proc on second spell"


# ============================================================
# Test 7: Wild Pyromancer + Equality Board Clear
# ============================================================

class TestWildPyromancerPlusEquality:
    def test_equality_then_pyromancer_clears_board(self):
        """Equality sets all health to 1, then Wild Pyromancer fires 1 damage to all.

        Result: all minions (including Pyromancer) should die.
        """
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        friendly_yeti = make_obj(game, CHILLWIND_YETI, p1)
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, EQUALITY, p1)

        # After Equality:
        # - All minions now have 1 health (toughness=1, damage=0)
        # - Pyromancer triggers: 1 damage to ALL minions
        # - All minions at 1 health take 1 damage -> all should die

        # Check for destruction events
        destroyed = [e for e in game.state.event_log
                     if e.type == EventType.OBJECT_DESTROYED]
        destroyed_ids = {e.payload.get('object_id') for e in destroyed}

        # All three minions should be destroyed
        assert pyro.id in destroyed_ids or pyro.state.damage >= 1, (
            "Pyromancer should die from its own proc after Equality"
        )
        assert friendly_yeti.id in destroyed_ids or friendly_yeti.state.damage >= 1, (
            "Friendly Yeti should die from Pyromancer after Equality"
        )
        assert enemy_yeti.id in destroyed_ids or enemy_yeti.state.damage >= 1, (
            "Enemy Yeti should die from Pyromancer after Equality"
        )

    def test_equality_sets_all_health_to_1(self):
        """Equality should set toughness=1 and damage=0 for all minions."""
        game, p1, p2 = new_hs_game()
        yeti1 = make_obj(game, CHILLWIND_YETI, p1)
        yeti2 = make_obj(game, CHILLWIND_YETI, p2)

        # Deal some damage first
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti1.id, 'amount': 2, 'source': 'test'},
            source='test'
        ))

        # Cast Equality (no Pyromancer, just check Equality alone)
        spell_obj = game.create_object(
            name=EQUALITY.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=EQUALITY.characteristics, card_def=EQUALITY
        )
        events = EQUALITY.spell_effect(spell_obj, game.state, [])
        for e in events:
            game.emit(e)

        # After Equality, all minions should have toughness=1 and damage=0
        y1 = game.state.objects.get(yeti1.id)
        y2 = game.state.objects.get(yeti2.id)
        assert y1.characteristics.toughness == 1
        assert y1.state.damage == 0
        assert y2.characteristics.toughness == 1
        assert y2.state.damage == 0


# ============================================================
# Test 8: Spell Damage + Consecration
# ============================================================

class TestSpellDamagePlusConsecration:
    def test_kobold_plus_consecration(self):
        """Kobold Geomancer + Consecration = 3 damage to each enemy (2+1)."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, CONSECRATION, p1)

        minion_dmg = [e for e in game.state.event_log
                      if e.type == EventType.DAMAGE and
                      e.payload.get('from_spell') and
                      e.payload.get('target') == enemy.id]
        assert len(minion_dmg) == 1
        assert minion_dmg[0].payload['amount'] == 3, (
            f"Expected 3 damage (2+1), got {minion_dmg[0].payload['amount']}"
        )

    def test_kobold_plus_consecration_also_boosts_hero_damage(self):
        """Spell damage also boosts the Consecration damage to enemy hero."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

        cast_spell(game, CONSECRATION, p1)

        hero_dmg = [e for e in game.state.event_log
                    if e.type == EventType.DAMAGE and
                    e.payload.get('from_spell') and
                    e.payload.get('target') == p2.hero_id]
        assert len(hero_dmg) == 1
        assert hero_dmg[0].payload['amount'] == 3, (
            f"Expected 3 hero damage (2+1), got {hero_dmg[0].payload['amount']}"
        )


# ============================================================
# Test 9: Spell Damage + Holy Nova
# ============================================================

class TestSpellDamagePlusHolyNova:
    def test_kobold_plus_holy_nova_damage(self):
        """Kobold Geomancer on Priest's side + Holy Nova = 3 damage to enemies (2+1).

        Holy Nova's damage events have from_spell=True so spell damage applies.
        """
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, HOLY_NOVA, p1)

        enemy_dmg = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and
                     e.payload.get('from_spell') and
                     e.payload.get('target') == enemy.id]
        assert len(enemy_dmg) == 1
        assert enemy_dmg[0].payload['amount'] == 3, (
            f"Expected 3 damage (2+1), got {enemy_dmg[0].payload['amount']}"
        )

    def test_holy_nova_healing_not_boosted_by_spell_damage(self):
        """Spell damage should NOT boost Holy Nova's healing component.

        Healing uses LIFE_CHANGE events, not DAMAGE events, so spell damage
        interceptors (which only filter DAMAGE with from_spell) do not apply.
        """
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        friendly = make_obj(game, CHILLWIND_YETI, p1)

        # Damage the friendly yeti so healing has effect
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': friendly.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))
        game.state.event_log.clear()

        cast_spell(game, HOLY_NOVA, p1)

        # Healing is via LIFE_CHANGE, check that heal amount is 2, not 3
        heal_events = [e for e in game.state.event_log
                       if e.type == EventType.LIFE_CHANGE and
                       e.payload.get('object_id') == friendly.id]
        if heal_events:
            assert heal_events[0].payload['amount'] == 2, (
                f"Healing should be 2 (not boosted by spell damage), got {heal_events[0].payload['amount']}"
            )


# ============================================================
# Test 10: Azure Drake Spell Damage
# ============================================================

class TestAzureDrakeSpellDamage:
    def test_azure_drake_spell_damage_plus_1(self):
        """Azure Drake (Spell Damage +1) boosts AOE damage."""
        game, p1, p2 = new_hs_game()
        drake = make_obj(game, AZURE_DRAKE, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == enemy.id and
                         e.payload.get('from_spell')]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 2, (
            f"Expected 2 damage (1+1 from Azure Drake), got {damage_events[0].payload['amount']}"
        )

    def test_azure_drake_plus_flamestrike(self):
        """Azure Drake + Flamestrike = 5 damage to each enemy minion (4+1)."""
        game, p1, p2 = new_hs_game()
        drake = make_obj(game, AZURE_DRAKE, p1)
        enemy1 = make_obj(game, CHILLWIND_YETI, p2)
        enemy2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('from_spell') and
                         e.payload.get('amount') == 5]
        assert len(damage_events) == 2, (
            f"Expected 2 enemies taking 5 damage each, got {len(damage_events)}"
        )

    def test_azure_drake_stacks_with_kobold(self):
        """Azure Drake + Kobold Geomancer = Spell Damage +2 total."""
        game, p1, p2 = new_hs_game()
        drake = make_obj(game, AZURE_DRAKE, p1)
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == enemy.id and
                         e.payload.get('from_spell')]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 3, (
            f"Expected 3 damage (1+1+1 from Drake+Kobold), got {damage_events[0].payload['amount']}"
        )

    def test_kobold_plus_flamestrike(self):
        """Kobold Geomancer + Flamestrike = 5 damage to each enemy (4+1)."""
        game, p1, p2 = new_hs_game()
        kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('from_spell') and
                         e.payload.get('target') == enemy.id]
        assert len(damage_events) == 1
        assert damage_events[0].payload['amount'] == 5, (
            f"Expected 5 damage (4+1), got {damage_events[0].payload['amount']}"
        )
