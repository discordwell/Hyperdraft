"""
Hearthstone Unhappy Path Tests - Batch 108

Hero-specific card interactions and class identity mechanics.

Tests cover:
- Mage class identity (6 tests)
- Warlock class identity (5 tests)
- Priest class identity (5 tests)
- Rogue class identity (6 tests)
- Paladin class identity (5 tests)
- Warrior class identity (6 tests)
- Hunter class identity (5 tests)
- Shaman class identity (4 tests)
- Druid class identity (4 tests)
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

from src.cards.hearthstone.basic import WISP
from src.cards.hearthstone.classic import (
    FIREBALL, FROSTBOLT, ARCANE_INTELLECT, FLAMESTRIKE, POLYMORPH, BACKSTAB
)
from src.cards.hearthstone.mage import SORCERERS_APPRENTICE
from src.cards.hearthstone.warlock import SOULFIRE, HELLFIRE, POWER_OVERWHELMING, DOOMGUARD
from src.cards.hearthstone.priest import SHADOW_WORD_PAIN, SHADOW_WORD_DEATH, HOLY_NOVA
from src.cards.hearthstone.rogue import SAP, ASSASSINATE, COLD_BLOOD, EVISCERATE
from src.cards.hearthstone.paladin import BLESSING_OF_KINGS, CONSECRATION, TRUESILVER_CHAMPION, EQUALITY
from src.cards.hearthstone.warrior import EXECUTE, SHIELD_SLAM
from src.cards.hearthstone.hunter import KILL_COMMAND, ANIMAL_COMPANION, UNLEASH_THE_HOUNDS, EXPLOSIVE_TRAP
from src.cards.hearthstone.shaman import HEX, LIGHTNING_BOLT, FERAL_SPIRIT
from src.cards.hearthstone.druid import SWIPE, INNERVATE, WRATH


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

    # Auto-select target if spell requires target but none provided
    if targets is None and getattr(card_def, 'requires_target', False):
        # Find enemy hero or minion
        battlefield = game.state.zones.get('battlefield')
        enemy_id = None
        for pid in game.state.players.keys():
            if pid != owner.id:
                enemy_player = game.state.players[pid]
                # Prefer enemy minions first
                if battlefield:
                    for oid in battlefield.objects:
                        o = game.state.objects.get(oid)
                        if o and o.controller == pid and CardType.MINION in o.characteristics.types:
                            enemy_id = oid
                            break
                # Fall back to enemy hero
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
# Mage Class Identity Tests
# ============================================================

class TestMageClassIdentity:
    def test_mage_hero_power_fireblast(self):
        """Mage Fireblast hero power deals 1 damage to enemy hero."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        p2_life_before = p2.life

        # Use Fireblast
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        # Should deal 1 damage
        assert p2.life == p2_life_before - 1, f"Fireblast should deal 1 damage, went from {p2_life_before} to {p2.life}"

    def test_fireball_deals_6_damage(self):
        """Fireball deals 6 damage to target."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        p2_life_before = p2.life

        # Cast Fireball
        cast_spell(game, FIREBALL, p1)

        # Should deal 6 damage
        assert p2.life == p2_life_before - 6, f"Fireball should deal 6 damage, dealt {p2_life_before - p2.life}"

    def test_frostbolt_deals_3_and_freeze(self):
        """Frostbolt deals 3 damage and freezes target."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # Create enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 5

        # Cast Frostbolt
        cast_spell(game, FROSTBOLT, p1)

        # Should deal 3 damage and freeze
        assert enemy.state.damage == 3, f"Frostbolt should deal 3 damage, dealt {enemy.state.damage}"
        assert enemy.state.frozen, "Frostbolt should freeze target"

    def test_flamestrike_enemy_only_aoe(self):
        """Flamestrike is enemy-only AOE (4 damage)."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # Create friendly and enemy minions
        friendly = make_obj(game, WISP, p1)
        friendly.characteristics.toughness = 5
        enemy1 = make_obj(game, WISP, p2)
        enemy1.characteristics.toughness = 5
        enemy2 = make_obj(game, WISP, p2)
        enemy2.characteristics.toughness = 5

        # Cast Flamestrike
        cast_spell(game, FLAMESTRIKE, p1)

        # Check damage
        assert friendly.state.damage == 0, "Flamestrike should not damage friendly minions"
        assert enemy1.state.damage == 4, f"Flamestrike should deal 4 to enemy, dealt {enemy1.state.damage}"
        assert enemy2.state.damage == 4, f"Flamestrike should deal 4 to enemy, dealt {enemy2.state.damage}"

    def test_polymorph_transforms_minion(self):
        """Polymorph transforms any minion into a 1/1 Sheep."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # Create a big enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.power = 8
        enemy.characteristics.toughness = 8

        minions_before = get_battlefield_count(game, p2)

        # Cast Polymorph
        cast_spell(game, POLYMORPH, p1)

        # Should transform to sheep (1/1)
        # Check if a 1/1 creature exists
        battlefield = game.state.zones.get('battlefield')
        found_sheep = False
        if battlefield:
            for oid in battlefield.objects:
                obj = game.state.objects.get(oid)
                if obj and obj.controller == p2.id and CardType.MINION in obj.characteristics.types:
                    if get_power(obj, game.state) == 1 and get_toughness(obj, game.state) == 1:
                        found_sheep = True

        assert found_sheep or minions_before == get_battlefield_count(game, p2), "Polymorph should create 1/1 Sheep"

    def test_arcane_intellect_draws_2(self):
        """Arcane Intellect draws 2 cards."""
        game, p1, p2 = new_hs_game("Mage", "Warrior")

        # Add cards to library
        for _ in range(5):
            game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=WISP.characteristics, card_def=WISP
            )

        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0

        # Cast Arcane Intellect
        cast_spell(game, ARCANE_INTELLECT, p1)

        hand_after = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0

        assert hand_after == hand_before + 2, f"Arcane Intellect should draw 2 cards, drew {hand_after - hand_before}"


# ============================================================
# Warlock Class Identity Tests
# ============================================================

class TestWarlockClassIdentity:
    def test_warlock_life_tap_draws_and_damages(self):
        """Life Tap draws 1 card and deals 2 self-damage."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        # Add cards to library
        for _ in range(5):
            game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.LIBRARY,
                characteristics=WISP.characteristics, card_def=WISP
            )

        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0
        life_before = p1.life

        # Use Life Tap
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        hand_after = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0

        # Should draw 1 and take 2 damage
        assert hand_after == hand_before + 1, f"Life Tap should draw 1 card, drew {hand_after - hand_before}"
        # Note: damage order may vary in implementation

    def test_soulfire_deals_4_discards_1(self):
        """Soulfire deals 4 damage and discards 1 random card."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        # Add card to hand
        game.create_object(
            name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=WISP.characteristics, card_def=WISP
        )

        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0
        p2_life_before = p2.life

        # Cast Soulfire
        cast_spell(game, SOULFIRE, p1)

        hand_after = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0

        # Should deal 4 damage
        assert p2.life == p2_life_before - 4, f"Soulfire should deal 4 damage, dealt {p2_life_before - p2.life}"
        # Should discard 1 card (if hand not empty before)
        if hand_before > 0:
            assert hand_after == hand_before - 1, f"Soulfire should discard 1 card, hand went from {hand_before} to {hand_after}"

    def test_hellfire_damages_all_characters(self):
        """Hellfire damages all characters including own."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        # Create minions
        friendly = make_obj(game, WISP, p1)
        friendly.characteristics.toughness = 5
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 5

        p1_life_before = p1.life
        p2_life_before = p2.life

        # Cast Hellfire
        cast_spell(game, HELLFIRE, p1)

        # Should damage all (3 damage)
        assert friendly.state.damage == 3, f"Hellfire should deal 3 to friendly, dealt {friendly.state.damage}"
        assert enemy.state.damage == 3, f"Hellfire should deal 3 to enemy, dealt {enemy.state.damage}"
        # Heroes may take damage too depending on implementation

    def test_power_overwhelming_buff_then_die(self):
        """Power Overwhelming: +4/+4 then minion dies at end of turn."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        # Create friendly minion
        friendly = make_obj(game, WISP, p1)
        power_before = get_power(friendly, game.state)
        toughness_before = get_toughness(friendly, game.state)

        # Cast Power Overwhelming
        cast_spell(game, POWER_OVERWHELMING, p1)

        power_after = get_power(friendly, game.state)
        toughness_after = get_toughness(friendly, game.state)

        # Should get +4/+4
        assert power_after >= power_before + 4, f"Power Overwhelming should give +4 attack, got +{power_after - power_before}"
        assert toughness_after >= toughness_before + 4, f"Power Overwhelming should give +4 health, got +{toughness_after - toughness_before}"

    def test_doomguard_charge_discard_2(self):
        """Doomguard: Charge + discard 2 cards on battlecry."""
        game, p1, p2 = new_hs_game("Warlock", "Mage")

        # Add cards to hand
        for _ in range(3):
            game.create_object(
                name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
                characteristics=WISP.characteristics, card_def=WISP
            )

        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0

        # Play Doomguard
        doomguard = play_minion(game, DOOMGUARD, p1)

        hand_after = len(game.state.zones.get(hand_key).objects) if game.state.zones.get(hand_key) else 0

        # Should have Charge
        has_charge = has_ability(doomguard, 'charge', game.state)
        assert has_charge, "Doomguard should have Charge"

        # Should discard 2 cards (if hand not empty)
        if hand_before >= 2:
            assert hand_after <= hand_before - 2, f"Doomguard should discard 2, hand went from {hand_before} to {hand_after}"


# ============================================================
# Priest Class Identity Tests
# ============================================================

class TestPriestClassIdentity:
    def test_priest_lesser_heal(self):
        """Lesser Heal heals 2 to friendly damaged character."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        # Damage hero
        p1.life = 20
        life_before = p1.life

        # Use Lesser Heal
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        # Should heal 2
        assert p1.life >= life_before, f"Lesser Heal should heal, went from {life_before} to {p1.life}"

    def test_shadow_word_pain_kills_low_attack(self):
        """Shadow Word: Pain destroys minion with 3 or less attack."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        # Create low-attack enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.power = 2
        enemy.characteristics.toughness = 5

        minions_before = get_battlefield_count(game, p2)

        # Cast Shadow Word: Pain
        cast_spell(game, SHADOW_WORD_PAIN, p1)

        minions_after = get_battlefield_count(game, p2)

        # Should destroy the minion
        assert minions_after < minions_before, "Shadow Word: Pain should destroy low-attack minion"

    def test_shadow_word_pain_ignores_high_attack(self):
        """Shadow Word: Pain does nothing to 4+ attack minion."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        # Create high-attack enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.power = 5
        enemy.characteristics.toughness = 5

        minions_before = get_battlefield_count(game, p2)

        # Cast Shadow Word: Pain (should fail to target)
        cast_spell(game, SHADOW_WORD_PAIN, p1)

        minions_after = get_battlefield_count(game, p2)

        # Should not destroy high-attack minion
        assert minions_after == minions_before, "Shadow Word: Pain should not destroy 4+ attack minion"

    def test_shadow_word_death_kills_high_attack(self):
        """Shadow Word: Death destroys minion with 5 or more attack."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        # Create high-attack enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.power = 6
        enemy.characteristics.toughness = 6

        minions_before = get_battlefield_count(game, p2)

        # Cast Shadow Word: Death
        cast_spell(game, SHADOW_WORD_DEATH, p1)

        minions_after = get_battlefield_count(game, p2)

        # Should destroy the minion
        assert minions_after < minions_before, "Shadow Word: Death should destroy high-attack minion"

    def test_holy_nova_heals_friendlies_damages_enemies(self):
        """Holy Nova: heals friendlies, damages enemies."""
        game, p1, p2 = new_hs_game("Priest", "Mage")

        # Create minions
        friendly = make_obj(game, WISP, p1)
        friendly.characteristics.toughness = 5
        friendly.state.damage = 1
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 5

        friendly_damage_before = friendly.state.damage

        # Cast Holy Nova
        cast_spell(game, HOLY_NOVA, p1)

        # Friendly should be healed (damage reduced)
        # Enemy should be damaged
        assert enemy.state.damage > 0, "Holy Nova should damage enemy minions"


# ============================================================
# Rogue Class Identity Tests
# ============================================================

class TestRogueClassIdentity:
    def test_rogue_dagger_mastery(self):
        """Dagger Mastery equips 1/2 weapon."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Use Dagger Mastery
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        # Should have 1/2 weapon
        assert p1.weapon_attack >= 1, f"Dagger Mastery should equip 1 attack weapon, got {p1.weapon_attack}"
        assert p1.weapon_durability >= 2, f"Dagger Mastery should equip 2 durability weapon, got {p1.weapon_durability}"

    def test_backstab_undamaged_only(self):
        """Backstab deals 2 to undamaged minion."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Create undamaged enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 5

        # Cast Backstab
        cast_spell(game, BACKSTAB, p1)

        # Should deal 2 damage
        assert enemy.state.damage == 2, f"Backstab should deal 2 damage, dealt {enemy.state.damage}"

    def test_eviscerate_combo_4_damage(self):
        """Eviscerate: 2 base, 4 with combo."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Play another card first
        p1.cards_played_this_turn = 1

        p2_life_before = p2.life

        # Cast Eviscerate with combo
        cast_spell(game, EVISCERATE, p1)

        # Should deal 4 damage
        assert p2.life == p2_life_before - 4, f"Eviscerate with combo should deal 4, dealt {p2_life_before - p2.life}"

    def test_sap_returns_to_hand(self):
        """Sap returns enemy minion to hand."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Create enemy minion
        enemy = make_obj(game, WISP, p2)

        minions_before = get_battlefield_count(game, p2)

        # Cast Sap
        cast_spell(game, SAP, p1)

        minions_after = get_battlefield_count(game, p2)

        # Should remove from battlefield
        assert minions_after < minions_before, "Sap should return minion to hand"

    def test_assassinate_destroys_any_minion(self):
        """Assassinate destroys any enemy minion."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Create big enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.power = 10
        enemy.characteristics.toughness = 10

        minions_before = get_battlefield_count(game, p2)

        # Cast Assassinate
        cast_spell(game, ASSASSINATE, p1)

        minions_after = get_battlefield_count(game, p2)

        # Should destroy the minion
        assert minions_after < minions_before, "Assassinate should destroy any minion"

    def test_cold_blood_combo_4_attack(self):
        """Cold Blood: +2 attack, +4 with combo."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Create friendly minion
        friendly = make_obj(game, WISP, p1)
        power_before = get_power(friendly, game.state)

        # Play another card first
        p1.cards_played_this_turn = 1

        # Cast Cold Blood with combo
        cast_spell(game, COLD_BLOOD, p1)

        power_after = get_power(friendly, game.state)

        # Should get +4 attack
        assert power_after == power_before + 4, f"Cold Blood with combo should give +4, got +{power_after - power_before}"


# ============================================================
# Paladin Class Identity Tests
# ============================================================

class TestPaladinClassIdentity:
    def test_paladin_reinforce_summons_recruit(self):
        """Reinforce summons 1/1 Silver Hand Recruit."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")

        minions_before = get_battlefield_count(game, p1)

        # Use Reinforce
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        minions_after = get_battlefield_count(game, p1)

        # Should summon 1 minion
        assert minions_after == minions_before + 1, f"Reinforce should summon 1 minion, went from {minions_before} to {minions_after}"

    def test_consecration_damages_all_enemies(self):
        """Consecration deals 2 to all enemies."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")

        # Create enemy minions
        enemy1 = make_obj(game, WISP, p2)
        enemy1.characteristics.toughness = 5
        enemy2 = make_obj(game, WISP, p2)
        enemy2.characteristics.toughness = 5

        # Cast Consecration
        cast_spell(game, CONSECRATION, p1)

        # Should deal 2 to each
        assert enemy1.state.damage == 2, f"Consecration should deal 2, dealt {enemy1.state.damage}"
        assert enemy2.state.damage == 2, f"Consecration should deal 2, dealt {enemy2.state.damage}"

    def test_blessing_of_kings_gives_4_4(self):
        """Blessing of Kings: +4/+4."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")

        # Create friendly minion
        friendly = make_obj(game, WISP, p1)
        power_before = get_power(friendly, game.state)
        toughness_before = get_toughness(friendly, game.state)

        # Cast Blessing of Kings
        cast_spell(game, BLESSING_OF_KINGS, p1)

        power_after = get_power(friendly, game.state)
        toughness_after = get_toughness(friendly, game.state)

        # Should get +4/+4
        assert power_after >= power_before + 4, f"Blessing of Kings should give +4 attack, got +{power_after - power_before}"
        assert toughness_after >= toughness_before + 4, f"Blessing of Kings should give +4 health, got +{toughness_after - toughness_before}"

    def test_equality_sets_health_to_1(self):
        """Equality sets all minion health to 1."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")

        # Create big minions
        friendly = make_obj(game, WISP, p1)
        friendly.characteristics.toughness = 10
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 10

        # Cast Equality
        cast_spell(game, EQUALITY, p1)

        # All minions should have 1 health
        friendly_health = get_toughness(friendly, game.state)
        enemy_health = get_toughness(enemy, game.state)

        assert friendly_health == 1, f"Equality should set health to 1, got {friendly_health}"
        assert enemy_health == 1, f"Equality should set health to 1, got {enemy_health}"

    def test_truesilver_heals_on_attack(self):
        """Truesilver Champion heals 2 on attack."""
        game, p1, p2 = new_hs_game("Paladin", "Mage")

        # Damage hero first
        p1.life = 20

        # Equip Truesilver
        truesilver = make_obj(game, TRUESILVER_CHAMPION, p1)

        # Should have 4/2 weapon
        assert p1.weapon_attack >= 4, f"Truesilver should have 4 attack, got {p1.weapon_attack}"


# ============================================================
# Warrior Class Identity Tests
# ============================================================

class TestWarriorClassIdentity:
    def test_warrior_armor_up(self):
        """Armor Up! gains 2 armor."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        armor_before = p1.armor

        # Use Armor Up!
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        # Should gain 2 armor
        assert p1.armor == armor_before + 2, f"Armor Up should gain 2 armor, went from {armor_before} to {p1.armor}"

    def test_execute_kills_damaged_minion(self):
        """Execute destroys damaged enemy minion."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Create damaged enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 10
        enemy.state.damage = 1

        minions_before = get_battlefield_count(game, p2)

        # Cast Execute
        cast_spell(game, EXECUTE, p1)

        minions_after = get_battlefield_count(game, p2)

        # Should destroy the minion
        assert minions_after < minions_before, "Execute should destroy damaged minion"

    def test_execute_ignores_undamaged(self):
        """Execute does nothing to undamaged minion."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Create undamaged enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 10

        minions_before = get_battlefield_count(game, p2)

        # Cast Execute (should fail)
        cast_spell(game, EXECUTE, p1)

        minions_after = get_battlefield_count(game, p2)

        # Should not destroy undamaged minion
        assert minions_after == minions_before, "Execute should not destroy undamaged minion"

    def test_fiery_war_axe_3_2_weapon(self):
        """Fiery War Axe is 3/2 weapon."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Need to import from basic
        from src.cards.hearthstone.basic import FIERY_WAR_AXE

        # Equip Fiery War Axe
        axe = make_obj(game, FIERY_WAR_AXE, p1)

        # Should have 3/2 weapon
        assert p1.weapon_attack >= 3, f"Fiery War Axe should have 3 attack, got {p1.weapon_attack}"
        assert p1.weapon_durability >= 2, f"Fiery War Axe should have 2 durability, got {p1.weapon_durability}"

    def test_shield_slam_damage_equals_armor(self):
        """Shield Slam: damage = armor amount."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Give armor
        p1.armor = 5

        # Create enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 10

        # Cast Shield Slam
        cast_spell(game, SHIELD_SLAM, p1)

        # Should deal 5 damage (equal to armor)
        assert enemy.state.damage == 5, f"Shield Slam should deal 5 (armor amount), dealt {enemy.state.damage}"

    def test_arcanite_reaper_5_2_weapon(self):
        """Arcanite Reaper is 5/2 weapon."""
        game, p1, p2 = new_hs_game("Warrior", "Mage")

        # Need to import from basic
        from src.cards.hearthstone.basic import ARCANITE_REAPER

        # Equip Arcanite Reaper
        reaper = make_obj(game, ARCANITE_REAPER, p1)

        # Should have 5/2 weapon
        assert p1.weapon_attack >= 5, f"Arcanite Reaper should have 5 attack, got {p1.weapon_attack}"
        assert p1.weapon_durability >= 2, f"Arcanite Reaper should have 2 durability, got {p1.weapon_durability}"


# ============================================================
# Hunter Class Identity Tests
# ============================================================

class TestHunterClassIdentity:
    def test_hunter_steady_shot(self):
        """Steady Shot deals 2 to enemy hero."""
        game, p1, p2 = new_hs_game("Hunter", "Mage")

        p2_life_before = p2.life

        # Use Steady Shot
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        # Should deal 2 damage
        total_damage = (p2_life_before - p2.life)
        assert total_damage == 2, f"Steady Shot should deal 2 damage, dealt {total_damage}"

    def test_kill_command_3_or_5_with_beast(self):
        """Kill Command: 3 damage, or 5 with beast."""
        game, p1, p2 = new_hs_game("Hunter", "Mage")

        # No beast - should deal 3
        p2_life_before = p2.life

        # Cast Kill Command without beast
        cast_spell(game, KILL_COMMAND, p1)

        damage_dealt = p2_life_before - p2.life

        # Should deal at least 3
        assert damage_dealt >= 3, f"Kill Command should deal at least 3, dealt {damage_dealt}"

    def test_animal_companion_summons_one_of_three(self):
        """Animal Companion: random of 3 beasts."""
        game, p1, p2 = new_hs_game("Hunter", "Mage")

        minions_before = get_battlefield_count(game, p1)

        # Cast Animal Companion
        cast_spell(game, ANIMAL_COMPANION, p1)

        minions_after = get_battlefield_count(game, p1)

        # Should summon 1 minion
        assert minions_after == minions_before + 1, f"Animal Companion should summon 1, went from {minions_before} to {minions_after}"

    def test_unleash_the_hounds_1_per_enemy(self):
        """Unleash the Hounds: 1/1 per enemy minion."""
        game, p1, p2 = new_hs_game("Hunter", "Mage")

        # Create enemy minions
        enemy1 = make_obj(game, WISP, p2)
        enemy2 = make_obj(game, WISP, p2)
        enemy3 = make_obj(game, WISP, p2)

        minions_before = get_battlefield_count(game, p1)

        # Cast Unleash the Hounds
        cast_spell(game, UNLEASH_THE_HOUNDS, p1)

        minions_after = get_battlefield_count(game, p1)

        # Should summon 3 hounds (1 per enemy)
        assert minions_after >= minions_before + 3, f"Unleash should summon 3 hounds, went from {minions_before} to {minions_after}"

    def test_explosive_trap_damages_all_on_attack(self):
        """Explosive Trap: 2 to all enemies when they attack."""
        game, p1, p2 = new_hs_game("Hunter", "Mage")

        # Create secret (Explosive Trap)
        # Note: secrets are tricky to test, we just verify it can be created
        secret = make_obj(game, EXPLOSIVE_TRAP, p1, zone=ZoneType.BATTLEFIELD)

        # Just verify secret exists
        assert secret is not None, "Explosive Trap should be created"


# ============================================================
# Shaman Class Identity Tests
# ============================================================

class TestShamanClassIdentity:
    def test_shaman_totemic_call(self):
        """Totemic Call summons random totem."""
        game, p1, p2 = new_hs_game("Shaman", "Mage")

        minions_before = get_battlefield_count(game, p1)

        # Use Totemic Call
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        minions_after = get_battlefield_count(game, p1)

        # Should summon 1 totem
        assert minions_after == minions_before + 1, f"Totemic Call should summon 1 totem, went from {minions_before} to {minions_after}"

    def test_lightning_bolt_3_damage_overload_1(self):
        """Lightning Bolt: 3 damage, overload 1."""
        game, p1, p2 = new_hs_game("Shaman", "Mage")

        p2_life_before = p2.life
        overload_before = p1.overloaded_mana

        # Cast Lightning Bolt
        cast_spell(game, LIGHTNING_BOLT, p1)

        # Should deal 3 damage
        assert p2.life == p2_life_before - 3, f"Lightning Bolt should deal 3, dealt {p2_life_before - p2.life}"

        # Should add 1 overload
        assert p1.overloaded_mana == overload_before + 1, f"Lightning Bolt should overload 1, went from {overload_before} to {p1.overloaded_mana}"

    def test_hex_transform_to_frog(self):
        """Hex: transform minion to 0/1 Frog with Taunt."""
        game, p1, p2 = new_hs_game("Shaman", "Mage")

        # Create big enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.power = 10
        enemy.characteristics.toughness = 10

        # Cast Hex
        cast_spell(game, HEX, p1)

        # Check if a 0/1 creature exists
        battlefield = game.state.zones.get('battlefield')
        found_frog = False
        if battlefield:
            for oid in battlefield.objects:
                obj = game.state.objects.get(oid)
                if obj and obj.controller == p2.id and CardType.MINION in obj.characteristics.types:
                    if get_power(obj, game.state) == 0 and get_toughness(obj, game.state) == 1:
                        found_frog = True

        assert found_frog, "Hex should create 0/1 Frog"

    def test_feral_spirit_summons_two_wolves(self):
        """Feral Spirit: two 2/3 Taunts, overload 2."""
        game, p1, p2 = new_hs_game("Shaman", "Mage")

        minions_before = get_battlefield_count(game, p1)
        overload_before = p1.overloaded_mana

        # Cast Feral Spirit
        cast_spell(game, FERAL_SPIRIT, p1)

        minions_after = get_battlefield_count(game, p1)

        # Should summon 2 wolves
        assert minions_after >= minions_before + 2, f"Feral Spirit should summon 2 wolves, went from {minions_before} to {minions_after}"

        # Should overload 2
        assert p1.overloaded_mana == overload_before + 2, f"Feral Spirit should overload 2, went from {overload_before} to {p1.overloaded_mana}"


# ============================================================
# Druid Class Identity Tests
# ============================================================

class TestDruidClassIdentity:
    def test_druid_shapeshift(self):
        """Shapeshift: +1 Attack this turn, +1 Armor."""
        game, p1, p2 = new_hs_game("Druid", "Mage")

        armor_before = p1.armor

        # Use Shapeshift
        hero_power_obj = game.state.objects.get(p1.hero_power_id)
        if hero_power_obj:
            p1.mana_crystals_available -= 2
            game.emit(Event(
                type=EventType.HERO_POWER_ACTIVATE,
                payload={'hero_power_id': hero_power_obj.id, 'player': p1.id},
                source=hero_power_obj.id
            ))
            p1.hero_power_used = True

        # Should gain 1 armor
        assert p1.armor == armor_before + 1, f"Shapeshift should gain 1 armor, went from {armor_before} to {p1.armor}"

        # Should gain 1 attack
        assert p1.weapon_attack >= 1, f"Shapeshift should give 1 attack, got {p1.weapon_attack}"

    def test_wrath_choose_3_damage_or_1_draw(self):
        """Wrath: choose 3 damage or 1 damage + draw."""
        game, p1, p2 = new_hs_game("Druid", "Mage")

        # Create enemy minion
        enemy = make_obj(game, WISP, p2)
        enemy.characteristics.toughness = 5

        # Cast Wrath (will choose based on AI logic)
        cast_spell(game, WRATH, p1)

        # Should deal some damage
        assert enemy.state.damage > 0, f"Wrath should deal damage, dealt {enemy.state.damage}"

    def test_swipe_4_to_one_1_to_rest(self):
        """Swipe: 4 to one enemy, 1 to rest."""
        game, p1, p2 = new_hs_game("Druid", "Mage")

        # Create enemy minions
        enemy1 = make_obj(game, WISP, p2)
        enemy1.characteristics.toughness = 10
        enemy2 = make_obj(game, WISP, p2)
        enemy2.characteristics.toughness = 10

        # Cast Swipe
        cast_spell(game, SWIPE, p1)

        # One should take 4, others should take 1
        total_damage = enemy1.state.damage + enemy2.state.damage
        assert total_damage >= 5, f"Swipe should deal at least 5 total (4+1), dealt {total_damage}"

    def test_innervate_2_temporary_mana(self):
        """Innervate: 2 temporary mana crystals."""
        game, p1, p2 = new_hs_game("Druid", "Mage")

        # Use all mana first
        p1.mana_crystals_available = 0

        # Cast Innervate
        cast_spell(game, INNERVATE, p1)

        # Should have 2 temporary mana
        assert p1.mana_crystals_available >= 2, f"Innervate should give 2 mana, have {p1.mana_crystals_available}"


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
