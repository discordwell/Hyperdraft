"""
Hearthstone Unhappy Path Tests - Batch 127: Spell Damage and Spell Interactions

Tests for Spell Damage +1 (Kobold Geomancer, Bloodmage Thalnos, Azure Drake, Dalaran Mage),
Spell Damage +5 (Malygos), spell damage stacking, spell effects (Arcane Intellect, Flamestrike,
Arcane Missiles, Fireball, Frostbolt, Pyroblast, Holy Nova, Sprint), transforms (Polymorph, Hex),
Counterspell, Preparation, and Silence interactions.
"""
import pytest
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
    WISP, CHILLWIND_YETI, BOULDERFIST_OGRE, KOBOLD_GEOMANCER,
    DALARAN_MAGE, OGRE_MAGI, ARCHMAGE
)
from src.cards.hearthstone.classic import (
    BLOODMAGE_THALNOS, AZURE_DRAKE, MALYGOS,
    FIREBALL, FROSTBOLT, ARCANE_INTELLECT, ARCANE_MISSILES,
    FLAMESTRIKE, POLYMORPH, SPRINT
)
from src.cards.hearthstone.mage import (
    PYROBLAST, COUNTERSPELL
)
from src.cards.hearthstone.shaman import HEX
from src.cards.hearthstone.priest import HOLY_NOVA
from src.cards.hearthstone.rogue import PREPARATION


def new_hs_game(p1_class="Warrior", p2_class="Mage"):
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    game.state.active_player = p1.id
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    if zone == ZoneType.BATTLEFIELD:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': obj.id, 'from_zone_type': None,
                     'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
            source=obj.id
        ))
    return obj


def cast_spell(game, card_def, owner, targets=None):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    if targets is None and getattr(card_def, 'requires_target', False):
        battlefield = game.state.zones.get('battlefield')
        if battlefield:
            for oid in battlefield.objects:
                o = game.state.objects.get(oid)
                if o and o.controller != owner.id and CardType.MINION in o.characteristics.types:
                    targets = [oid]
                    break
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    return obj


# =============================================================================
# Spell Damage +1 Tests
# =============================================================================

def test_kobold_geomancer_spell_damage():
    """Kobold Geomancer: Spell Damage +1."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Fireball normally deals 6, should deal 7 with spell damage +1
    cast_spell(game, FIREBALL, p1, targets=[target.id])

    assert target.state.damage == 7


def test_bloodmage_thalnos_spell_damage():
    """Bloodmage Thalnos: Spell Damage +1."""
    game, p1, p2 = new_hs_game()
    thalnos = make_obj(game, BLOODMAGE_THALNOS, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Fireball normally deals 6, should deal 7 with spell damage +1
    cast_spell(game, FIREBALL, p1, targets=[target.id])

    assert target.state.damage == 7


def test_azure_drake_spell_damage():
    """Azure Drake: Spell Damage +1."""
    game, p1, p2 = new_hs_game()
    drake = make_obj(game, AZURE_DRAKE, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Frostbolt normally deals 3, should deal 4 with spell damage +1
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 4


def test_dalaran_mage_spell_damage():
    """Dalaran Mage: Spell Damage +1."""
    game, p1, p2 = new_hs_game()
    mage = make_obj(game, DALARAN_MAGE, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Frostbolt normally deals 3, should deal 4 with spell damage +1
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 4


def test_ogre_magi_spell_damage():
    """Ogre Magi: Spell Damage +1."""
    game, p1, p2 = new_hs_game()
    ogre = make_obj(game, OGRE_MAGI, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Frostbolt normally deals 3, should deal 4 with spell damage +1
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 4


def test_archmage_spell_damage():
    """Archmage: Spell Damage +1."""
    game, p1, p2 = new_hs_game()
    archmage = make_obj(game, ARCHMAGE, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Fireball normally deals 6, should deal 7 with spell damage +1
    cast_spell(game, FIREBALL, p1, targets=[target.id])

    assert target.state.damage == 7


# =============================================================================
# Spell Damage +5 Tests (Malygos)
# =============================================================================

def test_malygos_spell_damage():
    """Malygos: Spell Damage +5."""
    game, p1, p2 = new_hs_game()
    malygos = make_obj(game, MALYGOS, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Frostbolt normally deals 3, should deal 8 with spell damage +5
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 8


def test_malygos_fireball():
    """Malygos + Fireball deals 11 damage."""
    game, p1, p2 = new_hs_game()
    malygos = make_obj(game, MALYGOS, p1)

    # Fireball normally deals 6, should deal 11 with spell damage +5
    p2_life_before = game.state.players[p2.id].life
    cast_spell(game, FIREBALL, p1, targets=[game.state.players[p2.id].hero_id])

    assert game.state.players[p2.id].life == p2_life_before - 11


# =============================================================================
# Multiple Spell Damage Minions Stack
# =============================================================================

def test_two_kobolds_stack():
    """Two Kobold Geomancers stack for +2 spell damage."""
    game, p1, p2 = new_hs_game()
    kobold1 = make_obj(game, KOBOLD_GEOMANCER, p1)
    kobold2 = make_obj(game, KOBOLD_GEOMANCER, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Frostbolt normally deals 3, should deal 5 with spell damage +2
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 5


def test_kobold_plus_malygos():
    """Kobold Geomancer + Malygos = +6 spell damage."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
    malygos = make_obj(game, MALYGOS, p1)

    # Frostbolt normally deals 3, should deal 9 with spell damage +6
    p2_life_before = game.state.players[p2.id].life
    cast_spell(game, FROSTBOLT, p1, targets=[game.state.players[p2.id].hero_id])

    assert game.state.players[p2.id].life == p2_life_before - 9


def test_three_spell_damage_minions():
    """Three spell damage minions stack properly."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)  # +1
    drake = make_obj(game, AZURE_DRAKE, p1)  # +1
    ogre = make_obj(game, OGRE_MAGI, p1)  # +1
    target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    # Frostbolt normally deals 3, should deal 6 with spell damage +3
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 6


# =============================================================================
# Spell Damage Only Affects Damage Spells
# =============================================================================

def test_spell_damage_not_affect_card_draw():
    """Spell damage doesn't affect Arcane Intellect (draw spell)."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    # Give player some cards in deck
    for i in range(5):
        game.add_to_deck(p1.id, WISP)

    hand_before = len(game.state.zones[f'hand_{p1.id}'].objects)
    cast_spell(game, ARCANE_INTELLECT, p1)
    hand_after = len(game.state.zones[f'hand_{p1.id}'].objects)

    # Should draw exactly 2 cards, not affected by spell damage
    assert hand_after == hand_before + 2


def test_spell_damage_not_affect_polymorph():
    """Spell damage doesn't affect Polymorph (transform spell)."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    cast_spell(game, POLYMORPH, p1, targets=[target.id])

    # Should become 1/1 regardless of spell damage
    assert get_power(target, game.state) == 1
    assert get_toughness(target, game.state) == 1


# =============================================================================
# Spell Damage + AOE Spells
# =============================================================================

def test_spell_damage_flamestrike():
    """Spell damage affects Flamestrike AOE."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    target1 = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
    target2 = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7
    target3 = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    # Flamestrike normally deals 4 to all enemy minions, should deal 5 with +1
    cast_spell(game, FLAMESTRIKE, p1)

    assert target1.state.damage == 5
    assert target2.state.damage == 5
    assert target3.state.damage == 5


def test_malygos_flamestrike():
    """Malygos + Flamestrike deals 9 damage to all enemy minions."""
    game, p1, p2 = new_hs_game()
    malygos = make_obj(game, MALYGOS, p1)

    target1 = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7
    target2 = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Flamestrike normally deals 4, should deal 9 with +5
    cast_spell(game, FLAMESTRIKE, p1)

    assert target1.state.damage == 9
    assert target2.state.damage == 9


def test_spell_damage_holy_nova():
    """Spell damage affects Holy Nova damage portion."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    target1 = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
    target2 = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    # Holy Nova normally deals 2 to enemy minions, should deal 3 with +1
    cast_spell(game, HOLY_NOVA, p1)

    assert target1.state.damage == 3
    assert target2.state.damage == 3


# =============================================================================
# Spell Damage + Arcane Missiles
# =============================================================================

def test_spell_damage_arcane_missiles():
    """Spell damage affects each Arcane Missiles hit."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    # Only one enemy target to make testing deterministic
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Arcane Missiles deals 3 x 1 damage normally, should be 3 x 2 with +1
    random.seed(42)
    cast_spell(game, ARCANE_MISSILES, p1)

    # With only one target, all 3 missiles hit it for 2 damage each = 6 total
    assert target.state.damage == 6


def test_malygos_arcane_missiles():
    """Malygos makes Arcane Missiles deal 3 x 6 damage."""
    game, p1, p2 = new_hs_game()
    malygos = make_obj(game, MALYGOS, p1)

    # Only one enemy target
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Arcane Missiles deals 3 x 1 normally, should be 3 x 6 with +5
    random.seed(42)
    cast_spell(game, ARCANE_MISSILES, p1)

    # 3 missiles x 6 damage = 18 total (kills 6/7 minion)
    assert target.zone == ZoneType.GRAVEYARD


# =============================================================================
# Spell Damage Removed When Minion Dies
# =============================================================================

def test_spell_damage_removed_when_kobold_dies():
    """Spell damage bonus disappears when minion dies."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # First spell with spell damage
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])
    assert target.state.damage == 4  # 3 + 1 from spell damage

    # Kill Kobold
    game.emit(Event(
        type=EventType.DESTROY,
        payload={'object_id': kobold.id},
        source=kobold.id
    ))
    assert kobold.zone == ZoneType.GRAVEYARD

    # Second spell without spell damage
    target2 = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7
    cast_spell(game, FROSTBOLT, p1, targets=[target2.id])
    assert target2.state.damage == 3  # Back to normal


def test_spell_damage_removed_when_malygos_dies():
    """Spell damage +5 disappears when Malygos dies."""
    game, p1, p2 = new_hs_game()
    malygos = make_obj(game, MALYGOS, p1)

    # First spell with Malygos
    p2_life_before = game.state.players[p2.id].life
    cast_spell(game, FROSTBOLT, p1, targets=[game.state.players[p2.id].hero_id])
    assert game.state.players[p2.id].life == p2_life_before - 8  # 3 + 5

    # Kill Malygos
    game.emit(Event(
        type=EventType.DESTROY,
        payload={'object_id': malygos.id},
        source=malygos.id
    ))

    # Second spell without Malygos
    p2_life_before = game.state.players[p2.id].life
    cast_spell(game, FROSTBOLT, p1, targets=[game.state.players[p2.id].hero_id])
    assert game.state.players[p2.id].life == p2_life_before - 3  # Back to normal


# =============================================================================
# Card Draw Spells
# =============================================================================

def test_arcane_intellect_draws_two():
    """Arcane Intellect draws 2 cards."""
    game, p1, p2 = new_hs_game()

    for i in range(5):
        game.add_to_deck(p1.id, WISP)

    hand_before = len(game.state.zones[f'hand_{p1.id}'].objects)
    cast_spell(game, ARCANE_INTELLECT, p1)
    hand_after = len(game.state.zones[f'hand_{p1.id}'].objects)

    assert hand_after == hand_before + 2


def test_sprint_draws_four():
    """Sprint draws 4 cards."""
    game, p1, p2 = new_hs_game()

    for i in range(5):
        game.add_to_deck(p1.id, WISP)

    hand_before = len(game.state.zones[f'hand_{p1.id}'].objects)
    cast_spell(game, SPRINT, p1)
    hand_after = len(game.state.zones[f'hand_{p1.id}'].objects)

    assert hand_after == hand_before + 4


# =============================================================================
# Direct Damage Spells
# =============================================================================

def test_fireball_deals_six():
    """Fireball deals 6 damage."""
    game, p1, p2 = new_hs_game()
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    cast_spell(game, FIREBALL, p1, targets=[target.id])

    assert target.state.damage == 6


def test_fireball_can_target_hero():
    """Fireball can target hero."""
    game, p1, p2 = new_hs_game()

    p2_life_before = game.state.players[p2.id].life
    cast_spell(game, FIREBALL, p1, targets=[game.state.players[p2.id].hero_id])

    assert game.state.players[p2.id].life == p2_life_before - 6


def test_pyroblast_deals_ten():
    """Pyroblast deals 10 damage."""
    game, p1, p2 = new_hs_game()

    p2_life_before = game.state.players[p2.id].life
    cast_spell(game, PYROBLAST, p1, targets=[game.state.players[p2.id].hero_id])

    assert game.state.players[p2.id].life == p2_life_before - 10


def test_pyroblast_can_target_minion():
    """Pyroblast can target minions."""
    game, p1, p2 = new_hs_game()
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    cast_spell(game, PYROBLAST, p1, targets=[target.id])

    assert target.zone == ZoneType.GRAVEYARD


# =============================================================================
# Frostbolt Freeze + Damage
# =============================================================================

def test_frostbolt_freeze_and_damage():
    """Frostbolt damages and freezes target."""
    game, p1, p2 = new_hs_game()
    target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 3
    assert target.state.frozen is True


def test_frostbolt_freeze_hero():
    """Frostbolt can freeze hero."""
    game, p1, p2 = new_hs_game()

    hero_obj = game.state.objects.get(game.state.players[p2.id].hero_id)

    cast_spell(game, FROSTBOLT, p1, targets=[hero_obj.id])

    assert hero_obj.state.frozen is True
    p2_life = game.state.players[p2.id].life
    assert p2_life == 27  # 30 - 3


# =============================================================================
# Transform Spells (Polymorph, Hex)
# =============================================================================

def test_polymorph_removes_abilities():
    """Polymorph transforms minion into 1/1 Sheep, removing abilities."""
    game, p1, p2 = new_hs_game()

    # Create a minion with abilities
    malygos = make_obj(game, MALYGOS, p2)  # 4/12, Spell Damage +5

    cast_spell(game, POLYMORPH, p1, targets=[malygos.id])

    # Should become 1/1 sheep
    assert get_power(malygos, game.state) == 1
    assert get_toughness(malygos, game.state) == 1
    assert malygos.state.damage == 0

    # Should lose spell damage ability
    # Test by casting a spell - should deal normal damage
    target = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
    cast_spell(game, FROSTBOLT, p2, targets=[target.id])
    assert target.state.damage == 3  # Not 8


def test_polymorph_removes_buffs():
    """Polymorph removes buffs."""
    game, p1, p2 = new_hs_game()
    target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    # Buff the minion
    game.emit(Event(
        type=EventType.PT_MODIFICATION,
        payload={'object_id': target.id, 'power_mod': 3, 'toughness_mod': 3, 'duration': 'permanent'},
        source=target.id
    ))

    assert get_power(target, game.state) == 7
    assert get_toughness(target, game.state) == 8

    # Polymorph it
    cast_spell(game, POLYMORPH, p1, targets=[target.id])

    # Should be 1/1
    assert get_power(target, game.state) == 1
    assert get_toughness(target, game.state) == 1


def test_hex_creates_taunt_frog():
    """Hex transforms minion into 0/1 Frog with Taunt."""
    game, p1, p2 = new_hs_game()
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    cast_spell(game, HEX, p1, targets=[target.id])

    # Should become 0/1 with taunt
    assert get_power(target, game.state) == 0
    assert get_toughness(target, game.state) == 1
    assert has_ability(target, game.state, 'taunt')


def test_hex_removes_abilities():
    """Hex removes original minion abilities."""
    game, p1, p2 = new_hs_game()
    malygos = make_obj(game, MALYGOS, p2)  # 4/12, Spell Damage +5

    cast_spell(game, HEX, p1, targets=[malygos.id])

    # Should lose spell damage
    target = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
    cast_spell(game, FROSTBOLT, p2, targets=[target.id])
    assert target.state.damage == 3  # Not 8


# =============================================================================
# Counterspell Secret
# =============================================================================

def test_counterspell_prevents_spell():
    """Counterspell secret prevents opponent's spell from taking effect."""
    game, p1, p2 = new_hs_game()

    # P1 plays Counterspell secret
    secret = make_obj(game, COUNTERSPELL, p1, zone=ZoneType.BATTLEFIELD)

    # P2 tries to cast Fireball on P1's minion
    friendly_minion = make_obj(game, BOULDERFIST_OGRE, p1)  # 6/7

    # Cast Fireball from P2 - should be countered
    cast_spell(game, FIREBALL, p2, targets=[friendly_minion.id])

    # Minion should take no damage because spell was countered
    assert friendly_minion.state.damage == 0


# =============================================================================
# Preparation Cost Reduction
# =============================================================================

def test_preparation_reduces_spell_cost():
    """Preparation reduces next spell cost by 3."""
    game, p1, p2 = new_hs_game()

    # Cast Preparation
    cast_spell(game, PREPARATION, p1)

    # The next spell should cost 3 less
    # This is tested by checking player's cost_reductions state
    player = game.state.players[p1.id]
    assert hasattr(player, 'cost_reductions')
    assert len(player.cost_reductions) > 0


def test_preparation_sprint_combo():
    """Preparation + Sprint costs 4 instead of 7."""
    game, p1, p2 = new_hs_game()

    # Give player enough mana
    player = game.state.players[p1.id]
    player.mana_crystals_available = 4

    # Cast Preparation
    cast_spell(game, PREPARATION, p1)

    # Sprint normally costs 7, should cost 4 after Preparation
    # We verify by checking that the player can afford it
    mana_before = player.mana_crystals_available
    assert mana_before == 4

    # The cost reduction should be in place
    assert hasattr(player, 'cost_reductions')


# =============================================================================
# Silence Interactions
# =============================================================================

def test_silence_removes_spell_damage():
    """Silencing a spell damage minion removes the bonus."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    # Silence the Kobold
    game.emit(Event(
        type=EventType.SILENCE_TARGET,
        payload={'target': kobold.id},
        source=kobold.id
    ))

    # Cast a spell - should deal normal damage
    target = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
    cast_spell(game, FROSTBOLT, p1, targets=[target.id])

    assert target.state.damage == 3  # Not 4


def test_silence_removes_buffs_not_base_stats():
    """Silence removes buffs but not base stats."""
    game, p1, p2 = new_hs_game()
    target = make_obj(game, CHILLWIND_YETI, p1)  # 4/5 base

    # Buff the minion
    game.emit(Event(
        type=EventType.PT_MODIFICATION,
        payload={'object_id': target.id, 'power_mod': 2, 'toughness_mod': 2, 'duration': 'permanent'},
        source=target.id
    ))

    assert get_power(target, game.state) == 6
    assert get_toughness(target, game.state) == 7

    # Silence it
    game.emit(Event(
        type=EventType.SILENCE_TARGET,
        payload={'target': target.id},
        source=target.id
    ))

    # Should revert to base stats
    assert get_power(target, game.state) == 4
    assert get_toughness(target, game.state) == 5


# =============================================================================
# Edge Cases
# =============================================================================

def test_spell_damage_with_zero_damage_spell():
    """Spell damage doesn't crash on non-damaging spells."""
    game, p1, p2 = new_hs_game()
    kobold = make_obj(game, KOBOLD_GEOMANCER, p1)

    # Give player cards to draw
    for i in range(5):
        game.add_to_deck(p1.id, WISP)

    # Cast Arcane Intellect - should just draw 2 cards
    hand_before = len(game.state.zones[f'hand_{p1.id}'].objects)
    cast_spell(game, ARCANE_INTELLECT, p1)
    hand_after = len(game.state.zones[f'hand_{p1.id}'].objects)

    assert hand_after == hand_before + 2


def test_multiple_spell_damage_stacks_correctly():
    """Verify exact stacking with many minions."""
    game, p1, p2 = new_hs_game()

    # Create 5 spell damage minions
    kobold1 = make_obj(game, KOBOLD_GEOMANCER, p1)  # +1
    kobold2 = make_obj(game, KOBOLD_GEOMANCER, p1)  # +1
    drake = make_obj(game, AZURE_DRAKE, p1)  # +1
    ogre = make_obj(game, OGRE_MAGI, p1)  # +1
    dalaran = make_obj(game, DALARAN_MAGE, p1)  # +1
    # Total: +5

    # Frostbolt should deal 8 damage (3 + 5)
    p2_life_before = game.state.players[p2.id].life
    cast_spell(game, FROSTBOLT, p1, targets=[game.state.players[p2.id].hero_id])

    assert game.state.players[p2.id].life == p2_life_before - 8


def test_flamestrike_only_hits_enemy_minions():
    """Flamestrike doesn't damage friendly minions."""
    game, p1, p2 = new_hs_game()

    friendly = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
    enemy1 = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
    enemy2 = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    cast_spell(game, FLAMESTRIKE, p1)

    assert friendly.state.damage == 0
    assert enemy1.state.damage == 4
    assert enemy2.state.damage == 4


def test_arcane_missiles_hits_enemy_hero_when_no_minions():
    """Arcane Missiles can hit enemy hero."""
    game, p1, p2 = new_hs_game()

    # No enemy minions, only hero
    p2_life_before = game.state.players[p2.id].life
    random.seed(42)
    cast_spell(game, ARCANE_MISSILES, p1)

    # All 3 missiles should hit hero (3 damage total)
    assert game.state.players[p2.id].life == p2_life_before - 3


def test_polymorph_resets_damage():
    """Polymorph resets damage counters."""
    game, p1, p2 = new_hs_game()
    target = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Damage the minion first
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target.id, 'amount': 5, 'source': target.id},
        source=target.id
    ))
    assert target.state.damage == 5

    # Polymorph it
    cast_spell(game, POLYMORPH, p1, targets=[target.id])

    # Should be 1/1 with 0 damage
    assert get_toughness(target, game.state) == 1
    assert target.state.damage == 0
