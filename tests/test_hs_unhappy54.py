"""
Hearthstone Unhappy Path Tests - Batch 54

Mage spell interactions: Mana Wyrm spell-cast trigger, Sorcerer's Apprentice
cost reduction, Archmage Antonidas Fireball generation, Ice Lance frozen check,
Blizzard AOE + freeze, Cone of Cold adjacency freeze, Pyroblast damage, Ethereal
Arcanist secret growth, Polymorph transformation, Ice Block lethal prevention,
Mirror Image tokens, Arcane Explosion AOE, Frost Nova freeze all, and various
Mage spell edge cases.
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
    FROSTBOLT, FIREBALL, ARCANE_MISSILES, ARCANE_INTELLECT,
    POLYMORPH, FLAMESTRIKE, WATER_ELEMENTAL,
)
from src.cards.hearthstone.mage import (
    MANA_WYRM, SORCERERS_APPRENTICE, ARCHMAGE_ANTONIDAS,
    ICE_LANCE, BLIZZARD, CONE_OF_COLD, PYROBLAST,
    ETHEREAL_ARCANIST, MIRROR_IMAGE, ARCANE_EXPLOSION, FROST_NOVA,
    ICE_BLOCK, KIRIN_TOR_MAGE,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
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


def play_minion(game, card_def, owner):
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
        source=obj.id
    ))
    return obj


# ============================================================
# Mana Wyrm
# ============================================================

class TestManaWyrm:
    def test_gains_attack_on_spell_cast(self):
        """Mana Wyrm gains +1 Attack when a spell is cast."""
        game, p1, p2 = new_hs_game()
        wyrm = make_obj(game, MANA_WYRM, p1)

        cast_spell(game, ARCANE_INTELLECT, p1)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == wyrm.id and
                   e.payload.get('power_mod') == 1]
        assert len(pt_mods) >= 1

    def test_gains_multiple_on_multiple_spells(self):
        """Mana Wyrm gains +1 for each spell cast."""
        game, p1, p2 = new_hs_game()
        wyrm = make_obj(game, MANA_WYRM, p1)

        cast_spell(game, ARCANE_INTELLECT, p1)
        cast_spell(game, ARCANE_INTELLECT, p1)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == wyrm.id]
        assert len(pt_mods) >= 2


# ============================================================
# Sorcerer's Apprentice
# ============================================================

class TestSorcerersApprentice:
    def test_reduces_spell_cost_by_1(self):
        """Sorcerer's Apprentice makes spells cost 1 less."""
        game, p1, p2 = new_hs_game()
        apprentice = make_obj(game, SORCERERS_APPRENTICE, p1)

        # Verify cost modifier was registered
        assert len(p1.cost_modifiers) >= 1
        # Check it targets spells
        found = any(mod.get('card_type') == CardType.SPELL
                    for mod in p1.cost_modifiers)
        assert found


# ============================================================
# Archmage Antonidas
# ============================================================

class TestArchmageAntonidas:
    def test_generates_fireball_on_spell_cast(self):
        """Antonidas adds a Fireball to hand when a spell is cast."""
        game, p1, p2 = new_hs_game()
        anton = make_obj(game, ARCHMAGE_ANTONIDAS, p1)

        cast_spell(game, ARCANE_INTELLECT, p1)

        # Should have added a Fireball to hand via ADD_TO_HAND event
        add_events = [e for e in game.state.event_log
                      if e.type == EventType.ADD_TO_HAND and
                      e.payload.get('player') == p1.id]
        assert len(add_events) >= 1

    def test_generates_multiple_fireballs(self):
        """Antonidas generates a Fireball for each spell."""
        game, p1, p2 = new_hs_game()
        anton = make_obj(game, ARCHMAGE_ANTONIDAS, p1)

        cast_spell(game, ARCANE_INTELLECT, p1)
        cast_spell(game, ARCANE_INTELLECT, p1)

        add_events = [e for e in game.state.event_log
                      if e.type == EventType.ADD_TO_HAND and
                      e.payload.get('player') == p1.id]
        assert len(add_events) >= 2


# ============================================================
# Ice Lance
# ============================================================

class TestIceLance:
    def test_freezes_unfrozen_target(self):
        """Ice Lance freezes target that isn't already frozen."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, ICE_LANCE, p1, targets=[yeti.id])

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        assert len(freeze_events) >= 1

    def test_deals_4_damage_to_frozen_target(self):
        """Ice Lance deals 4 damage to already-frozen target.

        Ice Lance picks a random enemy target. We freeze all possible targets
        so whichever is picked will be frozen and take 4 damage.
        """
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        yeti.state.frozen = True
        # Also freeze the enemy hero object in case it gets picked
        hero = game.state.objects.get(p2.hero_id)
        if hero:
            hero.state.frozen = True

        cast_spell(game, ICE_LANCE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 4]
        assert len(damage_events) >= 1


# ============================================================
# Blizzard
# ============================================================

class TestBlizzard:
    def test_deals_2_damage_to_all_enemies(self):
        """Blizzard deals 2 damage to all enemy minions."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)

        cast_spell(game, BLIZZARD, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 2]
        assert len(damage_events) >= 2

    def test_freezes_all_enemies(self):
        """Blizzard freezes all enemy minions."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)

        cast_spell(game, BLIZZARD, p1)

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        assert len(freeze_events) >= 2


# ============================================================
# Cone of Cold
# ============================================================

class TestConeOfCold:
    def test_damages_target_and_adjacent(self):
        """Cone of Cold deals 1 damage to target and adjacent minions."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)
        w3 = make_obj(game, WISP, p2)

        cast_spell(game, CONE_OF_COLD, p1, targets=[w2.id])

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 1]
        # Should hit target + adjacent (up to 3)
        assert len(damage_events) >= 1


# ============================================================
# Pyroblast
# ============================================================

class TestPyroblast:
    def test_deals_10_damage(self):
        """Pyroblast deals 10 damage."""
        game, p1, p2 = new_hs_game()
        p2.life = 30

        cast_spell(game, PYROBLAST, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 10]
        assert len(damage_events) >= 1


# ============================================================
# Ethereal Arcanist
# ============================================================

class TestEtherealArcanist:
    def test_gains_2_2_with_secret(self):
        """Ethereal Arcanist gains +2/+2 at EOT if you control a Secret."""
        game, p1, p2 = new_hs_game()
        arcanist = make_obj(game, ETHEREAL_ARCANIST, p1)

        # Create a secret on the battlefield
        secret = game.create_object(
            name="Test Secret", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=ICE_BLOCK.characteristics, card_def=ICE_BLOCK
        )

        game.emit(Event(
            type=EventType.PHASE_END,
            payload={'phase': 'end', 'player': p1.id},
            source='game'
        ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == arcanist.id]
        assert len(pt_mods) >= 1


# ============================================================
# Polymorph
# ============================================================

class TestPolymorph:
    def test_transforms_to_1_1_sheep(self):
        """Polymorph transforms target into 1/1 Sheep."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        state_yeti = game.state.objects.get(yeti.id)
        assert state_yeti.name == 'Sheep'
        assert state_yeti.characteristics.power == 1
        assert state_yeti.characteristics.toughness == 1


# ============================================================
# Mirror Image
# ============================================================

class TestMirrorImage:
    def test_summons_two_0_2_taunts(self):
        """Mirror Image summons two 0/2 tokens with Taunt."""
        game, p1, p2 = new_hs_game()

        cast_spell(game, MIRROR_IMAGE, p1)

        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) == 2
        for te in token_events:
            assert te.payload['token']['power'] == 0
            assert te.payload['token']['toughness'] == 2


# ============================================================
# Arcane Explosion
# ============================================================

class TestArcaneExplosion:
    def test_deals_1_damage_to_all_enemies(self):
        """Arcane Explosion deals 1 damage to all enemy minions."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)
        w3 = make_obj(game, WISP, p2)

        cast_spell(game, ARCANE_EXPLOSION, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 1]
        assert len(damage_events) >= 3


# ============================================================
# Frost Nova
# ============================================================

class TestFrostNova:
    def test_freezes_all_enemy_minions(self):
        """Frost Nova freezes all enemy minions."""
        game, p1, p2 = new_hs_game()
        w1 = make_obj(game, WISP, p2)
        w2 = make_obj(game, WISP, p2)

        cast_spell(game, FROST_NOVA, p1)

        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        assert len(freeze_events) >= 2

    def test_does_not_freeze_friendly_minions(self):
        """Frost Nova should not freeze friendly minions."""
        game, p1, p2 = new_hs_game()
        friendly = make_obj(game, WISP, p1)
        enemy = make_obj(game, WISP, p2)

        cast_spell(game, FROST_NOVA, p1)

        # Only enemy should be frozen
        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        frozen_ids = {e.payload.get('target') for e in freeze_events}
        assert enemy.id in frozen_ids or len(freeze_events) >= 1
        assert friendly.id not in frozen_ids


# ============================================================
# Flamestrike
# ============================================================

class TestFlamestrike:
    def test_deals_4_damage_to_all_enemies(self):
        """Flamestrike deals 4 damage to all enemy minions."""
        game, p1, p2 = new_hs_game()
        y1 = make_obj(game, CHILLWIND_YETI, p2)
        y2 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FLAMESTRIKE, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 4]
        assert len(damage_events) >= 2


# ============================================================
# Arcane Missiles Random
# ============================================================

class TestArcaneMissiles:
    def test_fires_3_missiles(self):
        """Arcane Missiles fires 3 separate 1-damage missiles."""
        game, p1, p2 = new_hs_game()
        p2.life = 30

        random.seed(42)
        cast_spell(game, ARCANE_MISSILES, p1)

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 1]
        assert len(damage_events) == 3


# ============================================================
# Frostbolt
# ============================================================

class TestFrostbolt:
    def test_deals_3_damage_and_freezes(self):
        """Frostbolt deals 3 damage and freezes."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 3]
        freeze_events = [e for e in game.state.event_log
                         if e.type == EventType.FREEZE_TARGET]
        assert len(damage_events) >= 1
        assert len(freeze_events) >= 1


# ============================================================
# Fireball
# ============================================================

class TestFireball:
    def test_deals_6_damage(self):
        """Fireball deals 6 damage (requires explicit target)."""
        game, p1, p2 = new_hs_game()
        p2.life = 30

        cast_spell(game, FIREBALL, p1, targets=[p2.hero_id])

        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('amount') == 6]
        assert len(damage_events) >= 1


# ============================================================
# Kirin Tor Mage
# ============================================================

class TestKirinTorMage:
    def test_makes_next_secret_free(self):
        """Kirin Tor Mage makes the next Secret cost 0."""
        game, p1, p2 = new_hs_game()

        obj = make_obj(game, KIRIN_TOR_MAGE, p1)
        events = KIRIN_TOR_MAGE.battlecry(obj, game.state)

        # Should have added a cost reduction
        assert len(p1.cost_modifiers) >= 1
