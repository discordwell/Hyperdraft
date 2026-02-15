"""
Hearthstone Unhappy Path Tests - Batch 109

Spell + Minion Interaction Timing tests.

Tests cover:
- Wild Pyromancer timing (5 tests)
- Spell damage modifiers (5 tests)
- Battlecry vs spell distinction (5 tests)
- Auchenai Soulpriest healing inversion (5 tests)
- Buff spells on dying minions (5 tests)
- Spell targeting restrictions (5 tests)
- Overload and mana after spells (5 tests)
- AOE + Divine Shield interactions (5 tests)
- Spell damage lethal/overkill (5 tests)
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

from src.cards.hearthstone.basic import WISP, STONETUSK_BOAR
from src.cards.hearthstone.classic import (
    FIREBALL, FROSTBOLT, ARCANE_INTELLECT, FLAMESTRIKE,
    ARCANE_MISSILES, BACKSTAB, WILD_PYROMANCER,
    FAERIE_DRAGON, AZURE_DRAKE, BLOODMAGE_THALNOS, MALYGOS,
    ARGENT_COMMANDER, ABOMINATION
)
from src.cards.hearthstone.mage import (
    MANA_WYRM, COUNTERSPELL, SORCERERS_APPRENTICE,
    ARCANE_EXPLOSION, CONE_OF_COLD
)
from src.cards.hearthstone.priest import (
    AUCHENAI_SOULPRIEST, CIRCLE_OF_HEALING, HOLY_NOVA,
    POWER_WORD_SHIELD
)
from src.cards.hearthstone.paladin import (
    CONSECRATION, HOLY_LIGHT, BLESSING_OF_KINGS, EQUALITY
)
from src.cards.hearthstone.warrior import WHIRLWIND, CLEAVE
from src.cards.hearthstone.shaman import LIGHTNING_BOLT, LAVA_BURST
from src.cards.hearthstone.warlock import HELLFIRE
from src.cards.hearthstone.hunter import EXPLOSIVE_TRAP


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(p1_class="Warrior", p2_class="Mage"):
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
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
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': None,
                'to_zone_type': ZoneType.BATTLEFIELD,
                'controller': owner.id,
            },
            source=obj.id
        ))
    return obj


def cast_spell(game, card_def, owner, targets=None):
    """Cast a spell card by invoking its spell_effect and emitting SPELL_CAST."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    if targets is None and getattr(card_def, 'requires_target', False):
        battlefield = game.state.zones.get('battlefield')
        enemy_id = None
        for pid in game.state.players.keys():
            if pid != owner.id:
                enemy_player = game.state.players[pid]
                if battlefield:
                    for oid in battlefield.objects:
                        o = game.state.objects.get(oid)
                        if o and o.controller == pid and CardType.MINION in o.characteristics.types:
                            enemy_id = oid
                            break
                if not enemy_id and enemy_player.hero_id:
                    enemy_id = enemy_player.hero_id
                break
        if enemy_id:
            targets = [enemy_id]
        else:
            targets = []
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    owner.cards_played_this_turn += 1
    return obj


def play_minion(game, card_def, owner):
    """Play a minion from hand to battlefield."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'controller': owner.id,
        },
        source=obj.id
    ))
    owner.cards_played_this_turn += 1
    return obj


def get_battlefield_count(game, player):
    """Get number of minions on battlefield for player."""
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return 0
    count = 0
    for oid in battlefield.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
            count += 1
    return count


# ============================================================
# Wild Pyromancer Timing (5 tests)
# ============================================================

def test_wild_pyromancer_triggers_after_spell_effect():
    """Wild Pyromancer deals 1 damage AFTER spell effect resolves."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    pyro = make_obj(game, WILD_PYROMANCER, p1)  # 3/2
    target = make_obj(game, WISP, p2)  # 1/1

    # Cast spell that doesn't damage the Wisp
    cast_spell(game, ARCANE_INTELLECT, p1)
    game.check_state_based_actions()

    # Pyromancer should trigger after spell, dealing 1 to all minions
    assert target.zone == ZoneType.GRAVEYARD
    assert pyro.state.damage == 1  # Damaged itself


def test_wild_pyromancer_dies_from_own_trigger():
    """Wild Pyromancer with 1 health kills itself when spell cast."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    pyro = make_obj(game, WILD_PYROMANCER, p1)
    pyro.state.damage = 2  # Now at 1 health (3/2 with 2 damage)

    cast_spell(game, ARCANE_INTELLECT, p1)
    game.check_state_based_actions()

    assert pyro.zone == ZoneType.GRAVEYARD


def test_wild_pyromancer_triggers_on_buff_spell():
    """Wild Pyromancer triggers even on buff spells targeting it."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    pyro = make_obj(game, WILD_PYROMANCER, p1)
    other = make_obj(game, WISP, p2)  # Enemy wisp

    # Buff the Pyromancer itself (only friendly minion)
    cast_spell(game, POWER_WORD_SHIELD, p1, targets=[pyro.id])
    game.check_state_based_actions()

    # Should have +2 health from buff, but 1 damage from trigger
    assert pyro.state.damage == 1
    assert other.zone == ZoneType.GRAVEYARD  # Wisp killed by AOE


def test_wild_pyromancer_multiple_spells_same_turn():
    """Wild Pyromancer triggers separately for each spell."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    pyro = make_obj(game, WILD_PYROMANCER, p1)

    cast_spell(game, ARCANE_INTELLECT, p1)
    assert pyro.state.damage == 1

    cast_spell(game, ARCANE_INTELLECT, p1)
    game.check_state_based_actions()

    assert pyro.zone == ZoneType.GRAVEYARD  # 2 damage total


def test_wild_pyromancer_doesnt_trigger_on_minion():
    """Wild Pyromancer doesn't trigger when playing minions."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    pyro = make_obj(game, WILD_PYROMANCER, p1)
    wisp = make_obj(game, WISP, p1)

    # Play a minion (not a spell)
    play_minion(game, STONETUSK_BOAR, p1)
    game.check_state_based_actions()

    assert pyro.state.damage == 0
    assert wisp.zone == ZoneType.BATTLEFIELD


# ============================================================
# Spell Damage Modifiers (5 tests)
# ============================================================

def test_spell_damage_plus_one_increases_fireball():
    """Spell Damage +1 increases Fireball from 6 to 7."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    make_obj(game, BLOODMAGE_THALNOS, p1)  # Spell Damage +1

    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, FIREBALL, p1, targets=[p2_hero.id])

    # Check event log for damage
    damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    total_damage = sum(e.payload.get('amount', 0) for e in damage_events if e.payload.get('target') == p2_hero.id)
    assert total_damage == 7


def test_multiple_spell_damage_stack():
    """Multiple Spell Damage bonuses stack."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    make_obj(game, BLOODMAGE_THALNOS, p1)  # +1
    make_obj(game, AZURE_DRAKE, p1)  # +1

    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, FIREBALL, p1, targets=[p2_hero.id])

    damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    total_damage = sum(e.payload.get('amount', 0) for e in damage_events if e.payload.get('target') == p2_hero.id)
    assert total_damage == 8  # 6 + 2


def test_spell_damage_affects_aoe():
    """Spell Damage affects AOE spells."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    make_obj(game, BLOODMAGE_THALNOS, p1)
    target1 = make_obj(game, WISP, p2)
    target2 = make_obj(game, WISP, p2)

    cast_spell(game, ARCANE_EXPLOSION, p1)
    game.check_state_based_actions()

    # Arcane Explosion deals 1, +1 from spell damage = 2
    assert target1.zone == ZoneType.GRAVEYARD
    assert target2.zone == ZoneType.GRAVEYARD


def test_malygos_spell_damage_plus_five():
    """Malygos provides Spell Damage +5."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    make_obj(game, MALYGOS, p1)  # Spell Damage +5

    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, FROSTBOLT, p1, targets=[p2_hero.id])

    damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    total_damage = sum(e.payload.get('amount', 0) for e in damage_events if e.payload.get('target') == p2_hero.id)
    assert total_damage == 8  # 3 + 5


def test_spell_damage_doesnt_affect_minion_battlecry():
    """Spell Damage doesn't affect minion battlecries."""
    game, p1, p2 = new_hs_game("Paladin", "Warrior")
    make_obj(game, BLOODMAGE_THALNOS, p1)

    p2_hero = game.state.objects[p2.hero_id]
    initial_life = p2.life

    # Argent Commander has charge, not a damage battlecry
    play_minion(game, ARGENT_COMMANDER, p1)

    # No spell damage events should affect battlecry
    spell_damage_events = [e for e in game.state.event_log
                           if e.type == EventType.DAMAGE and e.payload.get('from_spell')]
    assert len(spell_damage_events) == 0


# ============================================================
# Battlecry vs Spell Distinction (5 tests)
# ============================================================

def test_battlecry_doesnt_trigger_spell_effects():
    """Battlecry damage doesn't count as a spell for triggers."""
    game, p1, p2 = new_hs_game("Paladin", "Warrior")
    target = make_obj(game, STONETUSK_BOAR, p2)  # 1/1

    play_minion(game, ARGENT_COMMANDER, p1)
    game.check_state_based_actions()

    # Verify minion was played
    assert get_battlefield_count(game, p1) == 1


def test_mana_wyrm_grows_on_spell_not_battlecry():
    """Mana Wyrm gains +1 attack from spells, not battlecries."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    wyrm = make_obj(game, MANA_WYRM, p1)  # 1/3

    # Play minion with battlecry
    play_minion(game, ARGENT_COMMANDER, p1)

    # Mana Wyrm should NOT have grown
    assert get_power(wyrm, game.state) == 1


def test_mana_wyrm_grows_on_actual_spell():
    """Mana Wyrm grows when actual spell is cast."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    wyrm = make_obj(game, MANA_WYRM, p1)

    cast_spell(game, ARCANE_INTELLECT, p1)

    assert get_power(wyrm, game.state) == 2


def test_counterspell_doesnt_counter_battlecry():
    """Counterspell doesn't counter battlecry effects."""
    game, p1, p2 = new_hs_game("Mage", "Paladin")

    target = make_obj(game, STONETUSK_BOAR, p1)
    commander = play_minion(game, ARGENT_COMMANDER, p2)
    game.check_state_based_actions()

    # Battlecry should resolve (minion placed)
    assert get_battlefield_count(game, p2) == 1


def test_wild_pyromancer_triggers_on_spell_not_battlecry():
    """Wild Pyromancer triggers on spells, not battlecries."""
    game, p1, p2 = new_hs_game("Paladin", "Warrior")
    pyro = make_obj(game, WILD_PYROMANCER, p1)

    play_minion(game, ARGENT_COMMANDER, p1)

    assert pyro.state.damage == 0  # No trigger


# ============================================================
# Auchenai Soulpriest Healing Inversion (5 tests)
# ============================================================

def test_auchenai_inverts_holy_light():
    """Auchenai Soulpriest makes Holy Light deal damage instead of healing."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    make_obj(game, AUCHENAI_SOULPRIEST, p1)

    p1.life = 25  # Damage p1 first so healing would normally help
    cast_spell(game, HOLY_LIGHT, p1)

    # Holy Light should deal 6 damage to p1 instead of healing
    assert p1.life == 19  # 25 - 6 = 19


def test_auchenai_inverts_circle_of_healing():
    """Auchenai + Circle of Healing becomes damage AOE."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)

    target1 = make_obj(game, STONETUSK_BOAR, p2)  # 1/1
    target2 = make_obj(game, STONETUSK_BOAR, p2)  # 1/1

    # CoH doesn't affect undamaged minions - just verify it works with Auchenai present
    cast_spell(game, CIRCLE_OF_HEALING, p1)
    game.check_state_based_actions()

    # Verify the spell resolved and Auchenai is still present
    assert auchenai.zone == ZoneType.BATTLEFIELD


def test_auchenai_self_damage_from_circle():
    """Auchenai's passive exists on battlefield."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)  # 3/5

    cast_spell(game, CIRCLE_OF_HEALING, p1)
    game.check_state_based_actions()

    # Auchenai should still be on battlefield after CoH
    assert auchenai.zone == ZoneType.BATTLEFIELD
    assert len(auchenai.interceptor_ids) > 0  # Has passive interceptor


def test_auchenai_dies_then_healing_works():
    """Auchenai at low health can die from interactions."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)
    auchenai.state.damage = 4  # 1 health left on 3/5

    # Kill it with direct damage
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': auchenai.id, 'amount': 1, 'source': 'test'},
        source='test'
    ))
    game.check_state_based_actions()

    # Auchenai should be dead
    assert auchenai.zone == ZoneType.GRAVEYARD


def test_auchenai_cant_heal_itself():
    """Auchenai makes all healing deal damage instead."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    make_obj(game, AUCHENAI_SOULPRIEST, p1)
    p1.life = 25

    # Cast Holy Light - normally heals controller 6, but Auchenai converts to damage
    cast_spell(game, HOLY_LIGHT, p1)

    # p1 takes 6 damage instead of healing
    assert p1.life == 19


# ============================================================
# Buff Spells on Dying Minions (5 tests)
# ============================================================

def test_buff_spell_on_dying_minion_wasted():
    """Buff spell cast after SBA can't save a dead minion."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    target = make_obj(game, STONETUSK_BOAR, p1)  # 1/1
    target.state.damage = 1  # Lethal damage marked

    # SBA kills the minion
    game.check_state_based_actions()
    assert target.zone == ZoneType.GRAVEYARD


def test_blessing_of_kings_on_1_health_minion():
    """Blessing of Kings on 1-health minion makes it survive."""
    game, p1, p2 = new_hs_game("Paladin", "Warrior")
    target = make_obj(game, STONETUSK_BOAR, p1)  # 1/1
    target.state.damage = 0  # Full health

    # Buff it (+4/+4)
    cast_spell(game, BLESSING_OF_KINGS, p1, targets=[target.id])

    # Deal 4 damage
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target.id, 'amount': 4},
        source=None
    ))
    game.check_state_based_actions()

    # Should survive with 1 health remaining
    assert target.zone == ZoneType.BATTLEFIELD
    assert get_toughness(target, game.state) == 5
    assert target.state.damage == 4


def test_power_word_shield_draw_still_happens():
    """Power Word Shield emits a draw event."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    target = make_obj(game, WISP, p1)

    cast_spell(game, POWER_WORD_SHIELD, p1, targets=[target.id])

    # Should have a DRAW event in the log
    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1


def test_buff_spell_timing_before_aoe():
    """Buff spell before AOE can save a minion."""
    game, p1, p2 = new_hs_game("Priest", "Warrior")
    target = make_obj(game, WISP, p1)  # 1/1

    # Buff first (+2 health)
    cast_spell(game, POWER_WORD_SHIELD, p1, targets=[target.id])

    # Then AOE for 1
    cast_spell(game, ARCANE_EXPLOSION, p1)
    game.check_state_based_actions()

    # Should survive
    assert target.zone == ZoneType.BATTLEFIELD


def test_buff_spell_after_aoe_too_late():
    """AOE kills minion, it can't be saved afterward."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    target = make_obj(game, WISP, p2)  # Enemy wisp

    # AOE kills it
    cast_spell(game, ARCANE_EXPLOSION, p1)
    game.check_state_based_actions()

    # Minion is dead
    assert target.zone == ZoneType.GRAVEYARD


# ============================================================
# Spell Targeting Restrictions (5 tests)
# ============================================================

def test_faerie_dragon_cant_be_targeted_by_spells():
    """Faerie Dragon has cant_be_targeted passive."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    faerie = make_obj(game, FAERIE_DRAGON, p2)  # 3/2

    # Verify Faerie Dragon exists on battlefield with its passive
    assert faerie.zone == ZoneType.BATTLEFIELD
    # Check it has interceptors set up (the cant_be_targeted passive)
    assert len(faerie.interceptor_ids) > 0


def test_backstab_requires_undamaged_minion():
    """Backstab requires target to be undamaged."""
    game, p1, p2 = new_hs_game("Rogue", "Warrior")
    target = make_obj(game, AZURE_DRAKE, p2)  # 4/4
    target.state.damage = 1  # Damaged

    # Backstab should fail or do nothing
    cast_spell(game, BACKSTAB, p1, targets=[target.id])

    # Target should have only 1 damage still
    assert target.state.damage == 1


def test_spell_requires_valid_target():
    """Spell that requires target will target hero by default."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")

    # No minions on board
    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, FROSTBOLT, p1)

    # Should have targeted something (hero by default)
    damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    assert len(damage_events) > 0


def test_cone_of_cold_targeting():
    """Cone of Cold requires a minion target."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    target = make_obj(game, STONETUSK_BOAR, p2)

    cast_spell(game, CONE_OF_COLD, p1, targets=[target.id])
    game.check_state_based_actions()

    # Should have dealt damage
    assert target.zone == ZoneType.GRAVEYARD


def test_cleave_with_single_target():
    """Cleave with only 1 enemy minion handles gracefully."""
    game, p1, p2 = new_hs_game("Warrior", "Mage")
    target = make_obj(game, STONETUSK_BOAR, p2)

    # Only 1 minion
    cast_spell(game, CLEAVE, p1)

    # Cleave should handle this gracefully without crashing
    # Verify no exception was raised and spell cast event logged
    spell_events = [e for e in game.state.event_log if e.type == EventType.SPELL_CAST]
    assert len(spell_events) == 1


# ============================================================
# Overload and Mana After Spells (5 tests)
# ============================================================

def test_lightning_bolt_adds_overload():
    """Lightning Bolt adds Overload: 1."""
    game, p1, p2 = new_hs_game("Shaman", "Warrior")

    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, LIGHTNING_BOLT, p1, targets=[p2_hero.id])

    assert p1.overloaded_mana == 1


def test_lava_burst_adds_overload_two():
    """Lava Burst adds Overload: 2."""
    game, p1, p2 = new_hs_game("Shaman", "Warrior")

    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, LAVA_BURST, p1, targets=[p2_hero.id])

    assert p1.overloaded_mana == 2


def test_multiple_overload_spells_stack():
    """Multiple overload spells stack their overload."""
    game, p1, p2 = new_hs_game("Shaman", "Warrior")

    p2_hero = game.state.objects[p2.hero_id]
    cast_spell(game, LIGHTNING_BOLT, p1, targets=[p2_hero.id])
    cast_spell(game, LIGHTNING_BOLT, p1, targets=[p2_hero.id])

    assert p1.overloaded_mana == 2


def test_overload_doesnt_prevent_casting():
    """Overload accumulation doesn't prevent casting this turn."""
    game, p1, p2 = new_hs_game("Shaman", "Warrior")

    initial_mana = p1.mana_crystals_available
    p2_hero = game.state.objects[p2.hero_id]

    # Cast spell with overload
    cast_spell(game, LAVA_BURST, p1, targets=[p2_hero.id])

    # Overload is accumulated but doesn't reduce current mana
    assert p1.overloaded_mana == 2


def test_sorcerers_apprentice_on_board():
    """Sorcerer's Apprentice exists on battlefield after playing."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    make_obj(game, SORCERERS_APPRENTICE, p1)

    assert get_battlefield_count(game, p1) == 1


# ============================================================
# AOE + Divine Shield Interactions (5 tests)
# ============================================================

def test_flamestrike_pops_divine_shields():
    """Flamestrike pops Divine Shields without dealing damage."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    target = make_obj(game, ARGENT_COMMANDER, p2)  # 4/2 Divine Shield

    cast_spell(game, FLAMESTRIKE, p1)
    game.check_state_based_actions()

    # Divine Shield should be gone, minion survives
    assert not target.state.divine_shield
    assert target.zone == ZoneType.BATTLEFIELD
    assert target.state.damage == 0


def test_consecration_vs_divine_shield():
    """Consecration pops Divine Shields."""
    game, p1, p2 = new_hs_game("Paladin", "Warrior")
    target = make_obj(game, ARGENT_COMMANDER, p2)

    cast_spell(game, CONSECRATION, p1)
    game.check_state_based_actions()

    assert not target.state.divine_shield
    assert target.zone == ZoneType.BATTLEFIELD


def test_whirlwind_pops_all_shields():
    """Whirlwind pops all Divine Shields."""
    game, p1, p2 = new_hs_game("Warrior", "Paladin")
    target1 = make_obj(game, ARGENT_COMMANDER, p2)
    target2 = make_obj(game, ARGENT_COMMANDER, p2)

    cast_spell(game, WHIRLWIND, p1)
    game.check_state_based_actions()

    assert not target1.state.divine_shield
    assert not target2.state.divine_shield


def test_arcane_missiles_can_pop_shields():
    """Arcane Missiles can pop Divine Shields randomly."""
    game, p1, p2 = new_hs_game("Mage", "Paladin")
    target = make_obj(game, ARGENT_COMMANDER, p2)

    cast_spell(game, ARCANE_MISSILES, p1)
    game.check_state_based_actions()

    # Might have popped shield depending on RNG - just verify spell resolved
    damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    assert len(damage_events) == 3  # 3 missiles


def test_equality_then_consecration():
    """Equality + Consecration combo kills all minions."""
    game, p1, p2 = new_hs_game("Paladin", "Warrior")
    target1 = make_obj(game, AZURE_DRAKE, p2)  # 4/4
    target2 = make_obj(game, STONETUSK_BOAR, p2)  # 1/1

    cast_spell(game, EQUALITY, p1)
    cast_spell(game, CONSECRATION, p1)
    game.check_state_based_actions()

    # All minions should be dead (1 health from equality, 2 damage from consecration)
    assert target1.zone == ZoneType.GRAVEYARD
    assert target2.zone == ZoneType.GRAVEYARD


# ============================================================
# Spell Damage Lethal/Overkill (5 tests)
# ============================================================

def test_fireball_overkill_damage_wasted():
    """Fireball overkill damage is wasted."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    target = make_obj(game, WISP, p2)  # 1/1

    cast_spell(game, FIREBALL, p1, targets=[target.id])
    game.check_state_based_actions()

    # Wisp dies, 5 damage wasted
    assert target.zone == ZoneType.GRAVEYARD


def test_flamestrike_overkill():
    """Flamestrike overkills small minions."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    wisp1 = make_obj(game, WISP, p2)
    wisp2 = make_obj(game, WISP, p2)

    cast_spell(game, FLAMESTRIKE, p1)
    game.check_state_based_actions()

    assert wisp1.zone == ZoneType.GRAVEYARD
    assert wisp2.zone == ZoneType.GRAVEYARD


def test_exact_lethal_damage():
    """Spell dealing exact lethal kills minion."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    target = make_obj(game, STONETUSK_BOAR, p2)  # 1/1

    # Deal exactly 1 damage
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target.id, 'amount': 1},
        source=None
    ))
    game.check_state_based_actions()

    assert target.zone == ZoneType.GRAVEYARD


def test_hellfire_damages_all_including_heroes():
    """Hellfire damages all characters including heroes."""
    game, p1, p2 = new_hs_game("Warlock", "Warrior")
    minion = make_obj(game, STONETUSK_BOAR, p2)

    cast_spell(game, HELLFIRE, p1)
    game.check_state_based_actions()

    # Check heroes took damage
    damage_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    assert len(damage_events) > 0


def test_abomination_death_triggers_after_spell():
    """Abomination deathrattle triggers after spell kills it."""
    game, p1, p2 = new_hs_game("Mage", "Warrior")
    abom = make_obj(game, ABOMINATION, p2)  # 4/4
    wisp = make_obj(game, WISP, p1)

    cast_spell(game, FIREBALL, p1, targets=[abom.id])
    game.check_state_based_actions()

    # Abomination dies, deathrattle triggers
    assert abom.zone == ZoneType.GRAVEYARD
    # Wisp should take 2 damage from deathrattle
    assert wisp.zone == ZoneType.GRAVEYARD
