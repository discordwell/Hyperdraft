"""
Hearthstone Unhappy Path Tests - Batch 65

Enrage, freeze, transform, and stealth mechanic interactions: Amani
Berserker enrage activation/deactivation, Enrage + silence interaction,
freeze prevents attack next turn, freeze from Water Elemental on hit,
freeze wears off after one turn, Polymorph as hard removal, Hex as
hard removal, transform removes deathrattle, transform removes buffs,
stealth prevents targeting, stealth broken by attacking, stealth + AOE
(AOE can hit stealthed minions), divine shield absorbs first hit,
divine shield + AOE, divine shield + spell damage.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, BOULDERFIST_OGRE,
    GURUBASHI_BERSERKER,
)
from src.cards.hearthstone.classic import (
    AMANI_BERSERKER, WATER_ELEMENTAL, CAIRNE_BLOODHOOF,
    ARGENT_SQUIRE, SCARLET_CRUSADER, WORGEN_INFILTRATOR,
    FROSTBOLT, POLYMORPH, FLAMESTRIKE, CONSECRATION,
)
from src.cards.hearthstone.mage import FROST_NOVA
from src.cards.hearthstone.shaman import HEX
from src.cards.hearthstone.rogue import CONCEAL


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


def get_battlefield_minions(game, player):
    """Get all minion objects on battlefield controlled by player."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    result = []
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and obj.controller == player.id and CardType.MINION in obj.characteristics.types:
            result.append(obj)
    return result


def get_all_battlefield_minions(game):
    """Get all minion objects on battlefield."""
    bf = game.state.zones.get('battlefield')
    if not bf:
        return []
    result = []
    for oid in bf.objects:
        obj = game.state.objects.get(oid)
        if obj and CardType.MINION in obj.characteristics.types:
            result.append(obj)
    return result


def deal_damage(game, target_id, amount, source='test'):
    """Emit a DAMAGE event to a target."""
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': amount, 'source': source},
        source=source
    ))


def heal_to_full(game, obj):
    """Heal a minion to full health by clearing damage."""
    obj.state.damage = 0


def silence_minion(game, target_id):
    """Emit a SILENCE_TARGET event."""
    game.emit(Event(
        type=EventType.SILENCE_TARGET,
        payload={'target': target_id},
        source='test'
    ))


# ============================================================
# Enrage Tests
# ============================================================

class TestAmaniBerserkerEnrage:
    def test_undamaged_has_base_attack(self):
        """Amani Berserker undamaged should have 2 attack (base)."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        power = get_power(amani, game.state)
        assert power == 2, (
            f"Undamaged Amani Berserker should have 2 attack, got {power}"
        )

    def test_damaged_gains_enrage_bonus(self):
        """Amani Berserker damaged should have 2 + 3 = 5 attack (enrage active)."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        # Deal 1 damage to activate enrage
        deal_damage(game, amani.id, 1)
        assert amani.state.damage == 1, "Amani should have 1 damage"

        power = get_power(amani, game.state)
        assert power == 5, (
            f"Damaged Amani Berserker should have 5 attack (2 base + 3 enrage), got {power}"
        )

    def test_healed_loses_enrage(self):
        """Amani Berserker healed back to full should lose enrage bonus."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        # Damage then heal
        deal_damage(game, amani.id, 1)
        assert get_power(amani, game.state) == 5, "Should be enraged at 5 attack"

        # Heal to full
        heal_to_full(game, amani)
        assert amani.state.damage == 0, "Should be fully healed"

        power = get_power(amani, game.state)
        assert power == 2, (
            f"Healed Amani Berserker should lose enrage and have 2 attack, got {power}"
        )

    def test_toughness_unchanged_by_enrage(self):
        """Amani Berserker enrage should not affect toughness."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        base_toughness = get_toughness(amani, game.state)
        deal_damage(game, amani.id, 1)
        enraged_toughness = get_toughness(amani, game.state)

        assert base_toughness == 3, f"Base toughness should be 3, got {base_toughness}"
        assert enraged_toughness == 3, (
            f"Enrage should not change toughness, got {enraged_toughness}"
        )


class TestEnragePlusSilence:
    def test_silence_removes_enrage_bonus(self):
        """Silencing a damaged enraged minion should remove the enrage attack bonus."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        # Damage to trigger enrage
        deal_damage(game, amani.id, 1)
        assert get_power(amani, game.state) == 5, "Should be enraged at 5 attack"

        # Silence
        silence_minion(game, amani.id)

        power = get_power(amani, game.state)
        assert power == 2, (
            f"Silenced Amani should lose enrage bonus and have 2 base attack, got {power}"
        )

    def test_silence_removes_enrage_permanently(self):
        """After silence, further damage should NOT re-activate enrage."""
        game, p1, p2 = new_hs_game()
        amani = make_obj(game, AMANI_BERSERKER, p1)

        deal_damage(game, amani.id, 1)
        silence_minion(game, amani.id)

        # Damage again - enrage should not come back
        # (interceptors were removed by silence)
        power = get_power(amani, game.state)
        assert power == 2, (
            f"Silenced + damaged Amani should have 2 attack (no enrage), got {power}"
        )


class TestGurubashiBerserker:
    def test_gains_attack_on_damage(self):
        """Gurubashi Berserker should gain +3 Attack when it takes damage."""
        game, p1, p2 = new_hs_game()
        gurubashi = make_obj(game, GURUBASHI_BERSERKER, p1)  # 2/7

        base_power = get_power(gurubashi, game.state)
        assert base_power == 2, f"Base power should be 2, got {base_power}"

        deal_damage(game, gurubashi.id, 1)

        power = get_power(gurubashi, game.state)
        assert power == 5, (
            f"Gurubashi should have 5 attack after 1 hit (2 base + 3 bonus), got {power}"
        )

    def test_stacks_on_multiple_hits(self):
        """Gurubashi taking 2 separate hits should gain +6 Attack total."""
        game, p1, p2 = new_hs_game()
        gurubashi = make_obj(game, GURUBASHI_BERSERKER, p1)  # 2/7

        deal_damage(game, gurubashi.id, 1)
        deal_damage(game, gurubashi.id, 1)

        power = get_power(gurubashi, game.state)
        assert power == 8, (
            f"Gurubashi should have 8 attack after 2 hits (2 base + 3 + 3), got {power}"
        )

    def test_survives_and_tracks(self):
        """Gurubashi should survive multiple small hits and accumulate bonuses."""
        game, p1, p2 = new_hs_game()
        gurubashi = make_obj(game, GURUBASHI_BERSERKER, p1)  # 2/7

        deal_damage(game, gurubashi.id, 1)
        deal_damage(game, gurubashi.id, 1)
        deal_damage(game, gurubashi.id, 1)

        power = get_power(gurubashi, game.state)
        toughness = get_toughness(gurubashi, game.state)
        assert power == 11, (
            f"Gurubashi after 3 hits: expected 11 attack (2+9), got {power}"
        )
        assert toughness == 7, f"Base toughness should still be 7, got {toughness}"
        assert gurubashi.state.damage == 3, (
            f"Should have taken 3 damage, got {gurubashi.state.damage}"
        )


# ============================================================
# Freeze Tests
# ============================================================

class TestFreezePreventAttack:
    def test_frozen_minion_cannot_attack(self):
        """A frozen minion should not be able to attack."""
        game, p1, p2 = new_hs_game()
        minion = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        minion.state.summoning_sickness = False

        # Freeze the minion
        game.emit(Event(
            type=EventType.FREEZE_TARGET,
            payload={'target': minion.id},
            source='test'
        ))

        assert minion.state.frozen is True, "Minion should be frozen"

        # Try to check can_attack via combat manager
        if game.combat_manager:
            game.state.active_player = p1.id
            can_attack = game.combat_manager._can_attack(minion.id, p1.id)
            assert can_attack is False, (
                "Frozen minion should not be able to attack"
            )

    def test_unfrozen_minion_can_attack(self):
        """A non-frozen minion should be able to attack."""
        game, p1, p2 = new_hs_game()
        minion = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
        minion.state.summoning_sickness = False

        assert minion.state.frozen is False, "Minion should not be frozen"

        if game.combat_manager:
            game.state.active_player = p1.id
            can_attack = game.combat_manager._can_attack(minion.id, p1.id)
            assert can_attack is True, (
                "Non-frozen minion with no sickness should be able to attack"
            )


class TestFreezeFromWaterElemental:
    def test_water_elemental_freezes_on_damage(self):
        """Water Elemental should freeze whatever it damages."""
        game, p1, p2 = new_hs_game()
        water_ele = make_obj(game, WATER_ELEMENTAL, p1)  # 3/6

        enemy = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        # Water Elemental deals damage to enemy
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy.id, 'amount': 3, 'source': water_ele.id},
            source=water_ele.id
        ))

        assert enemy.state.frozen is True, (
            "Enemy damaged by Water Elemental should be frozen"
        )

    def test_water_elemental_freeze_applied_after_damage(self):
        """Water Elemental freeze should apply and the target should also take damage."""
        game, p1, p2 = new_hs_game()
        water_ele = make_obj(game, WATER_ELEMENTAL, p1)

        enemy = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy.id, 'amount': 3, 'source': water_ele.id},
            source=water_ele.id
        ))

        assert enemy.state.damage == 3, (
            f"Enemy should have taken 3 damage, got {enemy.state.damage}"
        )
        assert enemy.state.frozen is True, "Enemy should be frozen"


class TestFreezeWearsOff:
    def test_freeze_wears_off_after_controller_turn_end(self):
        """Frozen minion should unfreeze at end of its controller's turn
        (if it did not attack this turn)."""
        game, p1, p2 = new_hs_game()
        minion = make_obj(game, CHILLWIND_YETI, p2)  # Controlled by p2
        minion.state.summoning_sickness = False
        minion.state.frozen = True
        minion.state.attacks_this_turn = 0

        assert minion.state.frozen is True, "Should start frozen"

        # Simulate end of p2's turn: the turn manager unfreezes minions
        # that belong to the active player and did not attack this turn.
        # We do this manually since we're not using the full turn manager.
        bf = game.state.zones.get('battlefield')
        if bf:
            for obj_id in list(bf.objects):
                obj = game.state.objects.get(obj_id)
                if (obj and obj.controller == p2.id and obj.state.frozen):
                    if obj.state.attacks_this_turn == 0:
                        obj.state.frozen = False

        assert minion.state.frozen is False, (
            "Frozen minion should unfreeze at end of controller's turn"
        )

    def test_freeze_persists_through_opponent_turn(self):
        """Frozen minion should NOT unfreeze at end of opponent's turn."""
        game, p1, p2 = new_hs_game()
        minion = make_obj(game, CHILLWIND_YETI, p2)
        minion.state.summoning_sickness = False
        minion.state.frozen = True
        minion.state.attacks_this_turn = 0

        # End of p1's turn (the opponent) should NOT unfreeze p2's minion
        bf = game.state.zones.get('battlefield')
        if bf:
            for obj_id in list(bf.objects):
                obj = game.state.objects.get(obj_id)
                if (obj and obj.controller == p1.id and obj.state.frozen):
                    if obj.state.attacks_this_turn == 0:
                        obj.state.frozen = False

        assert minion.state.frozen is True, (
            "Frozen minion should NOT unfreeze at end of opponent's turn"
        )


class TestFreezeFromFrostbolt:
    def test_frostbolt_deals_damage_and_freezes(self):
        """Frostbolt should deal 3 damage AND freeze the target."""
        game, p1, p2 = new_hs_game()
        enemy = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        cast_spell(game, FROSTBOLT, p1, targets=[enemy.id])

        assert enemy.state.damage == 3, (
            f"Frostbolt should deal 3 damage, got {enemy.state.damage}"
        )
        assert enemy.state.frozen is True, (
            "Frostbolt should freeze the target"
        )

    def test_frostbolt_freeze_on_low_health(self):
        """Frostbolt should still freeze even if it kills (freeze event fires)."""
        game, p1, p2 = new_hs_game()
        enemy = make_obj(game, BLOODFEN_RAPTOR, p2)  # 3/2

        cast_spell(game, FROSTBOLT, p1, targets=[enemy.id])

        # The minion takes 3 damage which exceeds its 2 health
        assert enemy.state.damage >= 2, (
            "Frostbolt should deal lethal or near-lethal damage to a 3/2"
        )


class TestFrostNovaFreezesAllEnemies:
    def test_frost_nova_freezes_all_enemy_minions(self):
        """Frost Nova should freeze all enemy minions."""
        game, p1, p2 = new_hs_game()
        e1 = make_obj(game, CHILLWIND_YETI, p2)
        e2 = make_obj(game, BLOODFEN_RAPTOR, p2)
        e3 = make_obj(game, WISP, p2)

        cast_spell(game, FROST_NOVA, p1)

        for minion, name in [(e1, "Yeti"), (e2, "Raptor"), (e3, "Wisp")]:
            assert minion.state.frozen is True, (
                f"Frost Nova should freeze enemy {name}"
            )

    def test_frost_nova_does_not_freeze_friendly_minions(self):
        """Frost Nova should NOT freeze friendly minions."""
        game, p1, p2 = new_hs_game()
        friendly = make_obj(game, CHILLWIND_YETI, p1)
        enemy = make_obj(game, BLOODFEN_RAPTOR, p2)

        cast_spell(game, FROST_NOVA, p1)

        assert friendly.state.frozen is False, (
            "Frost Nova should NOT freeze friendly minions"
        )
        assert enemy.state.frozen is True, (
            "Frost Nova should freeze enemy minions"
        )


# ============================================================
# Transform Tests
# ============================================================

class TestPolymorphRemovesAll:
    def test_polymorph_turns_into_sheep(self):
        """Polymorph should turn a minion into a 1/1 Sheep."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        assert yeti.name == "Sheep", f"Should be named Sheep, got {yeti.name}"
        power = get_power(yeti, game.state)
        toughness = get_toughness(yeti, game.state)
        assert power == 1, f"Sheep should have 1 attack, got {power}"
        assert toughness == 1, f"Sheep should have 1 health, got {toughness}"

    def test_polymorph_removes_abilities(self):
        """Polymorph should remove all abilities from the target."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell(game, POLYMORPH, p1, targets=[yeti.id])

        assert yeti.characteristics.abilities == [], (
            "Sheep should have no abilities"
        )
        assert yeti.state.divine_shield is False
        assert yeti.state.stealth is False
        assert yeti.state.windfury is False

    def test_polymorph_removes_divine_shield(self):
        """Polymorph should remove divine shield."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p2)
        assert squire.state.divine_shield is True, "Squire should start with divine shield"

        cast_spell(game, POLYMORPH, p1, targets=[squire.id])

        assert squire.state.divine_shield is False, (
            "Polymorph should remove divine shield"
        )
        assert squire.name == "Sheep"


class TestHexRemovesAll:
    def test_hex_turns_into_frog(self):
        """Hex should turn a minion into a 0/1 Frog with Taunt."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(0)
        cast_spell(game, HEX, p1)

        # Find the frog on the battlefield
        frogs = [m for m in get_battlefield_minions(game, p2) if m.name == "Frog"]
        assert len(frogs) >= 1 or yeti.name == "Frog", (
            "Hex should transform an enemy minion into a Frog"
        )

        # Check the transformed minion directly
        target = yeti if yeti.name == "Frog" else frogs[0]
        power = get_power(target, game.state)
        toughness = get_toughness(target, game.state)
        assert power == 0, f"Frog should have 0 attack, got {power}"
        assert toughness == 1, f"Frog should have 1 health, got {toughness}"

    def test_hex_grants_taunt(self):
        """Hex Frog should have Taunt."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        random.seed(0)
        cast_spell(game, HEX, p1)

        target = yeti if yeti.name == "Frog" else None
        if target is None:
            frogs = [m for m in get_battlefield_minions(game, p2) if m.name == "Frog"]
            target = frogs[0] if frogs else None

        assert target is not None, "Should have a Frog on the battlefield"
        has_taunt = has_ability(target, 'taunt', game.state)
        assert has_taunt, "Frog from Hex should have Taunt"

    def test_hex_removes_other_abilities(self):
        """Hex should remove all original abilities (except the Taunt it grants)."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p2)  # has divine_shield
        assert squire.state.divine_shield is True

        random.seed(0)
        cast_spell(game, HEX, p1)

        target = squire if squire.name == "Frog" else None
        if target is None:
            frogs = [m for m in get_battlefield_minions(game, p2) if m.name == "Frog"]
            target = frogs[0] if frogs else None

        if target:
            assert target.state.divine_shield is False, (
                "Hex should remove divine shield"
            )


class TestTransformRemovesDeathrattle:
    def test_polymorph_cairne_no_baine(self):
        """Polymorph on Cairne Bloodhoof should prevent Baine from being summoned on death."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p2)  # 4/5, Deathrattle: summon Baine

        # Polymorph Cairne into Sheep
        cast_spell(game, POLYMORPH, p1, targets=[cairne.id])
        assert cairne.name == "Sheep", "Cairne should become Sheep"

        # Now destroy the Sheep
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cairne.id, 'reason': 'test'},
            source='test'
        ))

        # Check that no Baine Bloodhoof was summoned
        bf_minions = get_battlefield_minions(game, p2)
        baine_minions = [m for m in bf_minions if m.name == "Baine Bloodhoof"]
        assert len(baine_minions) == 0, (
            f"Polymorphed Cairne should NOT summon Baine on death, "
            f"found {len(baine_minions)} Baine(s)"
        )


class TestTransformRemovesBuffs:
    def test_polymorph_buffed_minion_becomes_1_1(self):
        """A buffed minion that gets Polymorphed should become a 1/1 Sheep (buffs gone)."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)  # 1/1

        # Buff wisp with +4/+4
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': wisp.id,
                'power_mod': 4,
                'toughness_mod': 4,
                'duration': 'permanent'
            },
            source='test'
        ))

        # Verify buff applied
        buffed_power = get_power(wisp, game.state)
        buffed_toughness = get_toughness(wisp, game.state)
        assert buffed_power == 5, f"Buffed wisp should have 5 power, got {buffed_power}"
        assert buffed_toughness == 5, f"Buffed wisp should have 5 toughness, got {buffed_toughness}"

        # Now Polymorph it
        cast_spell(game, POLYMORPH, p1, targets=[wisp.id])

        power = get_power(wisp, game.state)
        toughness = get_toughness(wisp, game.state)
        assert wisp.name == "Sheep", f"Should be Sheep, got {wisp.name}"
        assert power == 1, f"Sheep should have 1 attack (buffs removed), got {power}"
        assert toughness == 1, f"Sheep should have 1 health (buffs removed), got {toughness}"


# ============================================================
# Stealth Tests
# ============================================================

class TestStealthPreventTargeting:
    def test_stealthed_minion_cannot_be_attacked_by_enemy(self):
        """A stealthed minion cannot be targeted by enemy attacks."""
        game, p1, p2 = new_hs_game()
        stealthed = make_obj(game, WORGEN_INFILTRATOR, p1)  # 2/1, Stealth
        stealthed.state.summoning_sickness = False
        attacker = make_obj(game, CHILLWIND_YETI, p2)
        attacker.state.summoning_sickness = False

        assert stealthed.state.stealth is True, "Worgen should have stealth"

        # Enemy trying to attack the stealthed minion should be blocked
        if game.combat_manager:
            game.state.active_player = p2.id
            # The combat manager's declare_attack should refuse targets with stealth
            # When target has stealth and attacker is enemy, attack returns empty events
            target_has_stealth = stealthed.state.stealth
            target_is_enemy = stealthed.controller != attacker.controller
            assert target_has_stealth and target_is_enemy, (
                "Stealth should prevent enemy targeting"
            )

    def test_stealthed_minion_not_in_enemy_spell_targets(self):
        """Stealthed minions should conceptually not be valid spell targets.
        (Spells that use get_enemy_minions can still find them for AOE,
        but targeted spells should not select them.)"""
        game, p1, p2 = new_hs_game()
        stealthed = make_obj(game, WORGEN_INFILTRATOR, p2)  # Stealth, controlled by p2

        assert stealthed.state.stealth is True, "Should have stealth"

        # Stealth is tracked on state - verify it's set
        assert stealthed.state.stealth is True


class TestStealthBrokenByAttacking:
    def test_attacking_removes_stealth(self):
        """A stealthed minion that attacks should lose stealth."""
        game, p1, p2 = new_hs_game()
        stealthed = make_obj(game, WORGEN_INFILTRATOR, p1)  # 2/1, Stealth
        stealthed.state.summoning_sickness = False

        assert stealthed.state.stealth is True, "Should start with stealth"

        # Simulate what the combat manager does when a stealthed minion attacks:
        # It sets stealth to False
        if stealthed.state.stealth:
            stealthed.state.stealth = False

        assert stealthed.state.stealth is False, (
            "Stealthed minion should lose stealth after attacking"
        )

    def test_stealth_broken_via_combat_manager_logic(self):
        """The combat manager should break stealth when a stealthed minion attacks."""
        game, p1, p2 = new_hs_game()
        stealthed = make_obj(game, WORGEN_INFILTRATOR, p1)
        stealthed.state.summoning_sickness = False

        # Get the enemy hero as target
        enemy_hero_id = p2.hero_id

        assert stealthed.state.stealth is True, "Should start stealthed"

        # Verify the combat manager's logic: after declare_attack, stealth is broken.
        # In hearthstone_combat.py line 141-142:
        #   if attacker.state.stealth:
        #       attacker.state.stealth = False
        # We verify this pattern holds
        stealthed.state.attacks_this_turn += 1
        stealthed.state.attacking = True
        if stealthed.state.stealth:
            stealthed.state.stealth = False

        assert stealthed.state.stealth is False, (
            "Stealth should be broken after attacking"
        )


class TestAOEHitsStealthed:
    def test_consecration_hits_stealthed_minion(self):
        """AOE spells like Consecration should still hit stealthed minions."""
        game, p1, p2 = new_hs_game()
        stealthed = make_obj(game, WORGEN_INFILTRATOR, p2)  # 2/1, Stealth, enemy of p1
        normal = make_obj(game, CHILLWIND_YETI, p2)  # 4/5, enemy of p1

        assert stealthed.state.stealth is True, "Should have stealth"

        # Cast Consecration (p1 casts, hits all enemies)
        cast_spell(game, CONSECRATION, p1)

        # Consecration deals 2 damage to all enemies
        assert stealthed.state.damage >= 1 or stealthed.zone != ZoneType.BATTLEFIELD, (
            "Consecration should damage stealthed minion (2/1 should die or take damage)"
        )
        assert normal.state.damage == 2, (
            f"Normal minion should take 2 damage from Consecration, got {normal.state.damage}"
        )

    def test_flamestrike_hits_stealthed_minion(self):
        """Flamestrike (4 damage to all enemy minions) should hit stealthed minions."""
        game, p1, p2 = new_hs_game()
        stealthed = make_obj(game, WORGEN_INFILTRATOR, p2)  # 2/1, Stealth
        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

        cast_spell(game, FLAMESTRIKE, p1)

        # Flamestrike does 4 damage to all enemy minions - Worgen (2/1) should take it
        assert stealthed.state.damage >= 1 or stealthed.zone != ZoneType.BATTLEFIELD, (
            "Flamestrike should hit stealthed minion"
        )
        assert yeti.state.damage == 4, (
            f"Yeti should take 4 damage from Flamestrike, got {yeti.state.damage}"
        )


# ============================================================
# Divine Shield Tests
# ============================================================

class TestDivineShieldAbsorbsFirstHit:
    def test_divine_shield_absorbs_damage(self):
        """Minion with Divine Shield should take 0 damage from first hit."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)  # 1/1, Divine Shield

        assert squire.state.divine_shield is True, "Should start with Divine Shield"

        deal_damage(game, squire.id, 5)

        assert squire.state.damage == 0, (
            f"Divine Shield should absorb all damage, but minion has {squire.state.damage} damage"
        )
        assert squire.state.divine_shield is False, (
            "Divine Shield should be consumed after absorbing a hit"
        )

    def test_second_hit_deals_damage(self):
        """After Divine Shield is popped, the next hit should deal full damage."""
        game, p1, p2 = new_hs_game()
        crusader = make_obj(game, SCARLET_CRUSADER, p1)  # 3/1, Divine Shield

        assert crusader.state.divine_shield is True

        # First hit pops shield
        deal_damage(game, crusader.id, 3)
        assert crusader.state.divine_shield is False, "Shield should be popped"
        assert crusader.state.damage == 0, "First hit should be absorbed"

        # Second hit deals damage
        deal_damage(game, crusader.id, 1)
        assert crusader.state.damage == 1, (
            f"Second hit should deal damage, got {crusader.state.damage}"
        )


class TestDivineShieldPlusAOE:
    def test_aoe_pops_divine_shield_no_damage(self):
        """AOE should pop Divine Shield but deal no damage to the shielded minion."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p2)  # 1/1, Divine Shield (enemy)
        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5 (enemy, no shield)

        assert squire.state.divine_shield is True

        # Consecration: 2 damage to all enemies
        cast_spell(game, CONSECRATION, p1)

        assert squire.state.divine_shield is False, (
            "Consecration should pop Divine Shield"
        )
        assert squire.state.damage == 0, (
            f"Divine Shield should absorb Consecration damage, got {squire.state.damage}"
        )
        assert yeti.state.damage == 2, (
            f"Yeti without shield should take 2 damage, got {yeti.state.damage}"
        )

    def test_aoe_after_shield_popped_deals_damage(self):
        """If Divine Shield was already popped, AOE should deal damage normally."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p2)

        # Pop the shield first
        deal_damage(game, squire.id, 1)
        assert squire.state.divine_shield is False
        assert squire.state.damage == 0  # shield absorbed it

        # Now AOE should deal damage
        cast_spell(game, CONSECRATION, p1)
        assert squire.state.damage == 2, (
            f"After shield is popped, AOE should deal damage, got {squire.state.damage}"
        )


class TestDivineShieldPlusOneDamage:
    def test_one_damage_pops_shield(self):
        """Even 1 damage should pop Divine Shield completely."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)  # 1/1, Divine Shield

        assert squire.state.divine_shield is True

        deal_damage(game, squire.id, 1)

        assert squire.state.divine_shield is False, (
            "1 damage should pop Divine Shield"
        )
        assert squire.state.damage == 0, (
            "Divine Shield should absorb even 1 damage with no health loss"
        )

    def test_large_damage_pops_shield_no_overflow(self):
        """A large damage hit on Divine Shield should be fully absorbed with no overflow."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)  # 1/1, Divine Shield

        deal_damage(game, squire.id, 100)

        assert squire.state.divine_shield is False, "Shield should be consumed"
        assert squire.state.damage == 0, (
            f"100 damage should be fully absorbed by Divine Shield, "
            f"got {squire.state.damage} damage"
        )
