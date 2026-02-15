"""
Hearthstone Unhappy Path Tests - Batch 62

Warlock and Hunter class-specific mechanics: Life Tap hero power
self-damage and draw, Soulfire discard interaction, Doomguard discard,
Succubus discard, Flame Imp self-damage, Pit Lord self-damage, Voidwalker
taunt stat check, Blood Imp stealth and health buff, Dread Infernal
battlecry AOE, Jaraxxus hero replacement, Kill Command beast conditional,
Savannah Highmane deathrattle, Houndmaster beast buff battlecry,
Unleash the Hounds scaling, Animal Companion random summon, Multi-Shot,
Arcane Shot, Tracking card selection, Timber Wolf beast buff aura,
Starving Buzzard draw on beast summon.
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

from src.cards.hearthstone.basic import WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR

from src.cards.hearthstone.warlock import (
    SOULFIRE, VOIDWALKER, BLOOD_IMP, FLAME_IMP, PIT_LORD,
    DREAD_INFERNAL, DOOMGUARD, SUCCUBUS,
)

from src.cards.hearthstone.hunter import (
    ARCANE_SHOT, TRACKING, KILL_COMMAND, ANIMAL_COMPANION,
    HOUNDMASTER, MULTI_SHOT, UNLEASH_THE_HOUNDS,
    TIMBER_WOLF, STARVING_BUZZARD, SAVANNAH_HIGHMANE,
)


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Warlock"], HERO_POWERS["Warlock"])
    game.setup_hearthstone_player(p2, HEROES["Hunter"], HERO_POWERS["Hunter"])
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


def add_card_to_hand(game, card_def, owner):
    """Create a card in the player's hand zone."""
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )


def add_dummy_to_hand(game, owner, name="Dummy Card"):
    """Create a dummy card in the player's hand for discard testing."""
    from src.engine.game import make_minion
    dummy_def = make_minion(name=name, attack=1, health=1, mana_cost="{1}", text="")
    return game.create_object(
        name=dummy_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=dummy_def.characteristics, card_def=dummy_def
    )


def get_hand_objects(game, player):
    """Return list of object IDs in a player's hand."""
    hand_key = f"hand_{player.id}"
    hand = game.state.zones.get(hand_key)
    if hand:
        return list(hand.objects)
    return []


def get_battlefield_minions(game, controller_id=None):
    """Return list of minion objects on the battlefield, optionally filtered by controller."""
    battlefield = game.state.zones.get('battlefield')
    minions = []
    if battlefield:
        for oid in battlefield.objects:
            obj = game.state.objects.get(oid)
            if obj and CardType.MINION in obj.characteristics.types:
                if controller_id is None or obj.controller == controller_id:
                    minions.append(obj)
    return minions


# ============================================================
# Test 1: Soulfire Discard
# ============================================================

class TestSoulfireDiscard:
    """Soulfire deals 4 damage AND discards a random card from hand."""

    def test_soulfire_deals_4_damage(self):
        """Soulfire should deal 4 damage to an enemy target."""
        game, p1, p2 = new_hs_game()
        # Put a card in hand so discard doesn't fail
        dummy = add_dummy_to_hand(game, p1, "Filler")
        # Place an enemy minion to take damage
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        random.seed(42)

        soulfire_obj = game.create_object(
            name=SOULFIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SOULFIRE.characteristics, card_def=SOULFIRE
        )
        events = SOULFIRE.spell_effect(soulfire_obj, game.state, [])

        # Find the DAMAGE event
        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        assert len(damage_events) >= 1, "Soulfire should produce at least 1 DAMAGE event"
        assert damage_events[0].payload['amount'] == 4, (
            f"Soulfire should deal 4 damage, got {damage_events[0].payload['amount']}"
        )

    def test_soulfire_discards_a_card(self):
        """Soulfire should produce a DISCARD event for a random hand card."""
        game, p1, p2 = new_hs_game()
        dummy1 = add_dummy_to_hand(game, p1, "Card A")
        dummy2 = add_dummy_to_hand(game, p1, "Card B")
        # Need an enemy target for the damage
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        random.seed(0)

        soulfire_obj = game.create_object(
            name=SOULFIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SOULFIRE.characteristics, card_def=SOULFIRE
        )
        events = SOULFIRE.spell_effect(soulfire_obj, game.state, [])

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) == 1, (
            f"Soulfire should produce exactly 1 DISCARD event, got {len(discard_events)}"
        )
        discarded_id = discard_events[0].payload.get('object_id')
        assert discarded_id in (dummy1.id, dummy2.id), (
            "Discarded card should be one of the cards in hand"
        )

    def test_soulfire_no_hand_cards_still_damages(self):
        """With no cards in hand, Soulfire still deals 4 damage (no discard event)."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        random.seed(0)

        soulfire_obj = game.create_object(
            name=SOULFIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
            characteristics=SOULFIRE.characteristics, card_def=SOULFIRE
        )
        events = SOULFIRE.spell_effect(soulfire_obj, game.state, [])

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(damage_events) >= 1, "Should still deal damage with empty hand"
        assert len(discard_events) == 0, "Should not discard with empty hand"


# ============================================================
# Test 2: Doomguard Discard
# ============================================================

class TestDoomguardDiscard:
    """Doomguard battlecry discards 2 cards. With 0 cards, discards 0."""

    def test_doomguard_discards_2_cards(self):
        """With 3 cards in hand, Doomguard battlecry discards exactly 2."""
        game, p1, p2 = new_hs_game()
        d1 = add_dummy_to_hand(game, p1, "Card A")
        d2 = add_dummy_to_hand(game, p1, "Card B")
        d3 = add_dummy_to_hand(game, p1, "Card C")
        random.seed(0)

        doomguard = make_obj(game, DOOMGUARD, p1)
        events = DOOMGUARD.battlecry(doomguard, game.state)

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) == 2, (
            f"Doomguard should discard exactly 2 cards, got {len(discard_events)}"
        )
        # Verify the discarded IDs are from the hand
        discarded_ids = {e.payload['object_id'] for e in discard_events}
        hand_ids = {d1.id, d2.id, d3.id}
        assert discarded_ids.issubset(hand_ids), (
            "All discarded cards should be from the player's hand"
        )

    def test_doomguard_with_1_card_discards_1(self):
        """With only 1 card in hand, Doomguard discards only 1."""
        game, p1, p2 = new_hs_game()
        d1 = add_dummy_to_hand(game, p1, "Only Card")
        random.seed(0)

        doomguard = make_obj(game, DOOMGUARD, p1)
        events = DOOMGUARD.battlecry(doomguard, game.state)

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) == 1, (
            f"Doomguard should discard 1 card (only 1 available), got {len(discard_events)}"
        )

    def test_doomguard_with_empty_hand_no_crash(self):
        """With 0 cards in hand, Doomguard battlecry produces 0 discards and doesn't crash."""
        game, p1, p2 = new_hs_game()

        doomguard = make_obj(game, DOOMGUARD, p1)
        events = DOOMGUARD.battlecry(doomguard, game.state)

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) == 0, (
            f"Doomguard with empty hand should discard 0, got {len(discard_events)}"
        )

    def test_doomguard_has_charge(self):
        """Doomguard should have the Charge keyword."""
        game, p1, p2 = new_hs_game()
        doomguard = make_obj(game, DOOMGUARD, p1)
        assert 'charge' in doomguard.characteristics.keywords, (
            f"Doomguard should have Charge keyword, got {doomguard.characteristics.keywords}"
        )


# ============================================================
# Test 3: Flame Imp Self-Damage
# ============================================================

class TestFlameImpSelfDamage:
    """Flame Imp battlecry deals 3 damage to your hero."""

    def test_flame_imp_battlecry_damages_own_hero(self):
        """Flame Imp battlecry should produce a 3-damage event targeting own hero."""
        game, p1, p2 = new_hs_game()
        flame_imp = make_obj(game, FLAME_IMP, p1)
        events = FLAME_IMP.battlecry(flame_imp, game.state)

        assert len(events) == 1, f"Should produce 1 DAMAGE event, got {len(events)}"
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 3
        assert events[0].payload['target'] == p1.hero_id, (
            "Flame Imp should damage own hero"
        )

    def test_flame_imp_battlecry_emitted_reduces_hero_life(self):
        """Emitting Flame Imp's battlecry damage actually reduces hero HP."""
        game, p1, p2 = new_hs_game()
        flame_imp = make_obj(game, FLAME_IMP, p1)
        life_before = p1.life

        events = FLAME_IMP.battlecry(flame_imp, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == life_before - 3, (
            f"Hero should have lost 3 life, was {life_before}, now {p1.life}"
        )

    def test_flame_imp_is_3_2(self):
        """Flame Imp should be a 3/2."""
        game, p1, p2 = new_hs_game()
        flame_imp = make_obj(game, FLAME_IMP, p1)
        assert flame_imp.characteristics.power == 3
        assert flame_imp.characteristics.toughness == 2


# ============================================================
# Test 4: Dread Infernal Battlecry
# ============================================================

class TestDreadInfernalBattlecry:
    """Dread Infernal deals 1 damage to ALL other characters on entry."""

    def test_dread_infernal_damages_other_minions(self):
        """Dread Infernal battlecry deals 1 damage to other minions."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        infernal = make_obj(game, DREAD_INFERNAL, p1)
        events = DREAD_INFERNAL.battlecry(infernal, game.state)

        # Should damage both wisp and yeti (but not self)
        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        damaged_targets = {e.payload['target'] for e in damage_events}

        assert wisp.id in damaged_targets, "Should damage friendly Wisp"
        assert yeti.id in damaged_targets, "Should damage enemy Yeti"
        assert infernal.id not in damaged_targets, "Should NOT damage self"

    def test_dread_infernal_damages_all_heroes(self):
        """Dread Infernal battlecry deals 1 damage to both heroes."""
        game, p1, p2 = new_hs_game()
        infernal = make_obj(game, DREAD_INFERNAL, p1)
        events = DREAD_INFERNAL.battlecry(infernal, game.state)

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        damaged_targets = {e.payload['target'] for e in damage_events}

        assert p1.hero_id in damaged_targets, "Should damage own hero"
        assert p2.hero_id in damaged_targets, "Should damage enemy hero"

    def test_dread_infernal_all_damage_is_1(self):
        """All damage events from Dread Infernal should be exactly 1."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p2)
        infernal = make_obj(game, DREAD_INFERNAL, p1)
        events = DREAD_INFERNAL.battlecry(infernal, game.state)

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        for de in damage_events:
            assert de.payload['amount'] == 1, (
                f"All Dread Infernal damage should be 1, got {de.payload['amount']}"
            )

    def test_dread_infernal_is_6_6(self):
        """Dread Infernal should be a 6/6."""
        game, p1, p2 = new_hs_game()
        infernal = make_obj(game, DREAD_INFERNAL, p1)
        assert infernal.characteristics.power == 6
        assert infernal.characteristics.toughness == 6


# ============================================================
# Test 5: Voidwalker Stats
# ============================================================

class TestVoidwalkerStats:
    """Voidwalker is a 1/3 with Taunt."""

    def test_voidwalker_power(self):
        game, p1, p2 = new_hs_game()
        vw = make_obj(game, VOIDWALKER, p1)
        assert vw.characteristics.power == 1, (
            f"Voidwalker should have 1 attack, got {vw.characteristics.power}"
        )

    def test_voidwalker_toughness(self):
        game, p1, p2 = new_hs_game()
        vw = make_obj(game, VOIDWALKER, p1)
        assert vw.characteristics.toughness == 3, (
            f"Voidwalker should have 3 health, got {vw.characteristics.toughness}"
        )

    def test_voidwalker_has_taunt(self):
        game, p1, p2 = new_hs_game()
        vw = make_obj(game, VOIDWALKER, p1)
        assert 'taunt' in vw.characteristics.keywords, (
            f"Voidwalker should have Taunt, keywords: {vw.characteristics.keywords}"
        )

    def test_voidwalker_is_demon(self):
        game, p1, p2 = new_hs_game()
        vw = make_obj(game, VOIDWALKER, p1)
        assert 'Demon' in vw.characteristics.subtypes, (
            f"Voidwalker should be a Demon, subtypes: {vw.characteristics.subtypes}"
        )


# ============================================================
# Test 6: Blood Imp Stealth
# ============================================================

class TestBloodImpStealth:
    """Blood Imp has Stealth."""

    def test_blood_imp_has_stealth_keyword(self):
        game, p1, p2 = new_hs_game()
        blood_imp = make_obj(game, BLOOD_IMP, p1)
        assert 'stealth' in blood_imp.characteristics.keywords, (
            f"Blood Imp should have Stealth keyword, got {blood_imp.characteristics.keywords}"
        )

    def test_blood_imp_is_0_1(self):
        game, p1, p2 = new_hs_game()
        blood_imp = make_obj(game, BLOOD_IMP, p1)
        assert blood_imp.characteristics.power == 0, (
            f"Blood Imp should have 0 attack, got {blood_imp.characteristics.power}"
        )
        assert blood_imp.characteristics.toughness == 1, (
            f"Blood Imp should have 1 health, got {blood_imp.characteristics.toughness}"
        )

    def test_blood_imp_is_demon(self):
        game, p1, p2 = new_hs_game()
        blood_imp = make_obj(game, BLOOD_IMP, p1)
        assert 'Demon' in blood_imp.characteristics.subtypes, (
            f"Blood Imp should be a Demon, subtypes: {blood_imp.characteristics.subtypes}"
        )


# ============================================================
# Test 7: Pit Lord Self-Damage
# ============================================================

class TestPitLordSelfDamage:
    """Pit Lord battlecry deals 5 damage to your hero."""

    def test_pit_lord_battlecry_damages_own_hero(self):
        """Pit Lord battlecry should produce a 5-damage event targeting own hero."""
        game, p1, p2 = new_hs_game()
        pit_lord = make_obj(game, PIT_LORD, p1)
        events = PIT_LORD.battlecry(pit_lord, game.state)

        assert len(events) == 1, f"Should produce 1 DAMAGE event, got {len(events)}"
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 5
        assert events[0].payload['target'] == p1.hero_id, (
            "Pit Lord should damage own hero"
        )

    def test_pit_lord_battlecry_emitted_reduces_hero_life(self):
        """Emitting Pit Lord's battlecry damage actually reduces hero HP by 5."""
        game, p1, p2 = new_hs_game()
        pit_lord = make_obj(game, PIT_LORD, p1)
        life_before = p1.life

        events = PIT_LORD.battlecry(pit_lord, game.state)
        for e in events:
            game.emit(e)

        assert p1.life == life_before - 5, (
            f"Hero should have lost 5 life, was {life_before}, now {p1.life}"
        )

    def test_pit_lord_is_5_6(self):
        """Pit Lord should be a 5/6."""
        game, p1, p2 = new_hs_game()
        pit_lord = make_obj(game, PIT_LORD, p1)
        assert pit_lord.characteristics.power == 5
        assert pit_lord.characteristics.toughness == 6


# ============================================================
# Test 8: Kill Command Beast Conditional
# ============================================================

class TestKillCommandBeastConditional:
    """Kill Command deals 3 damage normally, 5 with a Beast."""

    def test_kill_command_3_damage_without_beast(self):
        """Without a Beast on board, Kill Command deals 3 damage."""
        game, p1, p2 = new_hs_game()
        target_yeti = make_obj(game, CHILLWIND_YETI, p2)

        kc_obj = game.create_object(
            name=KILL_COMMAND.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
        )
        events = KILL_COMMAND.spell_effect(kc_obj, game.state, [target_yeti.id])

        assert len(events) == 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 3, (
            f"Kill Command without Beast should deal 3, got {events[0].payload['amount']}"
        )

    def test_kill_command_5_damage_with_beast(self):
        """With a Beast on board, Kill Command deals 5 damage."""
        game, p1, p2 = new_hs_game()
        # Place a beast for p2 (the caster)
        timber_wolf = make_obj(game, TIMBER_WOLF, p2)
        target_yeti = make_obj(game, CHILLWIND_YETI, p1)

        kc_obj = game.create_object(
            name=KILL_COMMAND.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
        )
        events = KILL_COMMAND.spell_effect(kc_obj, game.state, [target_yeti.id])

        assert len(events) == 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 5, (
            f"Kill Command with Beast should deal 5, got {events[0].payload['amount']}"
        )

    def test_kill_command_enemy_beast_does_not_count(self):
        """An enemy Beast should NOT enable the bonus damage."""
        game, p1, p2 = new_hs_game()
        # Beast belongs to p1 (enemy of caster p2)
        enemy_beast = make_obj(game, TIMBER_WOLF, p1)
        target_yeti = make_obj(game, CHILLWIND_YETI, p1)

        kc_obj = game.create_object(
            name=KILL_COMMAND.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=KILL_COMMAND.characteristics, card_def=KILL_COMMAND
        )
        events = KILL_COMMAND.spell_effect(kc_obj, game.state, [target_yeti.id])

        assert events[0].payload['amount'] == 3, (
            f"Enemy Beast should not count: expected 3 damage, got {events[0].payload['amount']}"
        )


# ============================================================
# Test 9: Savannah Highmane Deathrattle
# ============================================================

class TestSavannahHighmaneDeathrattle:
    """Savannah Highmane deathrattle summons 2x 2/2 Hyena tokens."""

    def test_highmane_deathrattle_produces_two_tokens(self):
        """Deathrattle should produce exactly 2 CREATE_TOKEN events."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p2)

        # Directly invoke the deathrattle function from the card def
        events = SAVANNAH_HIGHMANE.deathrattle(highmane, game.state)
        assert len(events) == 2, (
            f"Highmane deathrattle should produce 2 CREATE_TOKEN events, got {len(events)}"
        )

    def test_highmane_tokens_are_hyenas(self):
        """The tokens should be named Hyena."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p2)
        events = SAVANNAH_HIGHMANE.deathrattle(highmane, game.state)

        for e in events:
            assert e.type == EventType.CREATE_TOKEN
            token = e.payload['token']
            assert token['name'] == 'Hyena', f"Token should be Hyena, got {token['name']}"

    def test_highmane_tokens_are_2_2_beasts(self):
        """Hyena tokens should be 2/2 Beasts."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p2)
        events = SAVANNAH_HIGHMANE.deathrattle(highmane, game.state)

        for e in events:
            token = e.payload['token']
            assert token['power'] == 2, f"Hyena should have 2 power, got {token['power']}"
            assert token['toughness'] == 2, f"Hyena should have 2 toughness, got {token['toughness']}"
            assert 'Beast' in token['subtypes'], f"Hyena should be Beast, got {token['subtypes']}"

    def test_highmane_is_6_5_beast(self):
        """Savannah Highmane should be a 6/5 Beast."""
        game, p1, p2 = new_hs_game()
        highmane = make_obj(game, SAVANNAH_HIGHMANE, p2)
        assert highmane.characteristics.power == 6
        assert highmane.characteristics.toughness == 5
        assert 'Beast' in highmane.characteristics.subtypes


# ============================================================
# Test 10: Houndmaster Beast Buff
# ============================================================

class TestHoundmasterBeastBuff:
    """Houndmaster battlecry gives a friendly Beast +2/+2 and Taunt."""

    def test_houndmaster_buffs_friendly_beast(self):
        """Houndmaster battlecry should produce PT_MODIFICATION and KEYWORD_GRANT events for a Beast."""
        game, p1, p2 = new_hs_game()
        # Place a beast for p2
        raptor = make_obj(game, BLOODFEN_RAPTOR, p2)
        houndmaster = make_obj(game, HOUNDMASTER, p2)
        random.seed(0)

        events = HOUNDMASTER.battlecry(houndmaster, game.state)

        pt_events = [e for e in events if e.type == EventType.PT_MODIFICATION]
        kw_events = [e for e in events if e.type == EventType.KEYWORD_GRANT]

        assert len(pt_events) >= 1, "Houndmaster should produce a PT_MODIFICATION event"
        assert pt_events[0].payload['power_mod'] == 2
        assert pt_events[0].payload['toughness_mod'] == 2
        assert pt_events[0].payload['object_id'] == raptor.id

        assert len(kw_events) >= 1, "Houndmaster should grant Taunt"
        assert kw_events[0].payload['keyword'] == 'taunt'
        assert kw_events[0].payload['object_id'] == raptor.id

    def test_houndmaster_no_beast_no_buff(self):
        """Without a friendly Beast on board, Houndmaster battlecry does nothing."""
        game, p1, p2 = new_hs_game()
        # Only a non-Beast minion on board
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        houndmaster = make_obj(game, HOUNDMASTER, p2)

        events = HOUNDMASTER.battlecry(houndmaster, game.state)
        assert len(events) == 0, (
            f"Houndmaster with no Beast should produce 0 events, got {len(events)}"
        )

    def test_houndmaster_does_not_buff_enemy_beast(self):
        """Houndmaster should only buff friendly Beasts, not enemy ones."""
        game, p1, p2 = new_hs_game()
        # Beast belongs to p1 (enemy of houndmaster's controller p2)
        enemy_raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        houndmaster = make_obj(game, HOUNDMASTER, p2)

        events = HOUNDMASTER.battlecry(houndmaster, game.state)
        assert len(events) == 0, (
            "Houndmaster should not buff enemy Beast"
        )


# ============================================================
# Test 11: Unleash the Hounds Scaling
# ============================================================

class TestUnleashTheHoundsScaling:
    """Unleash creates 1/1 Hounds equal to number of enemy minions."""

    def test_unleash_creates_hounds_matching_enemy_count(self):
        """With 3 enemy minions, Unleash creates 3 Hound tokens."""
        game, p1, p2 = new_hs_game()
        make_obj(game, WISP, p1)
        make_obj(game, WISP, p1)
        make_obj(game, WISP, p1)

        uth_obj = game.create_object(
            name=UNLEASH_THE_HOUNDS.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=UNLEASH_THE_HOUNDS.characteristics, card_def=UNLEASH_THE_HOUNDS
        )
        events = UNLEASH_THE_HOUNDS.spell_effect(uth_obj, game.state, [])

        token_events = [e for e in events if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) == 3, (
            f"Should create 3 Hounds for 3 enemy minions, got {len(token_events)}"
        )

    def test_unleash_zero_enemy_minions(self):
        """With 0 enemy minions, Unleash creates 0 Hounds."""
        game, p1, p2 = new_hs_game()

        uth_obj = game.create_object(
            name=UNLEASH_THE_HOUNDS.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=UNLEASH_THE_HOUNDS.characteristics, card_def=UNLEASH_THE_HOUNDS
        )
        events = UNLEASH_THE_HOUNDS.spell_effect(uth_obj, game.state, [])

        token_events = [e for e in events if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) == 0, (
            f"Should create 0 Hounds with no enemies, got {len(token_events)}"
        )

    def test_unleash_hounds_have_charge(self):
        """Hound tokens should have the Charge keyword."""
        game, p1, p2 = new_hs_game()
        make_obj(game, WISP, p1)

        uth_obj = game.create_object(
            name=UNLEASH_THE_HOUNDS.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=UNLEASH_THE_HOUNDS.characteristics, card_def=UNLEASH_THE_HOUNDS
        )
        events = UNLEASH_THE_HOUNDS.spell_effect(uth_obj, game.state, [])

        for e in events:
            token = e.payload['token']
            assert 'charge' in token.get('keywords', set()), (
                f"Hound should have Charge, got {token.get('keywords')}"
            )

    def test_unleash_hounds_are_1_1_beasts(self):
        """Hound tokens should be 1/1 Beasts."""
        game, p1, p2 = new_hs_game()
        make_obj(game, WISP, p1)

        uth_obj = game.create_object(
            name=UNLEASH_THE_HOUNDS.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=UNLEASH_THE_HOUNDS.characteristics, card_def=UNLEASH_THE_HOUNDS
        )
        events = UNLEASH_THE_HOUNDS.spell_effect(uth_obj, game.state, [])

        token = events[0].payload['token']
        assert token['power'] == 1
        assert token['toughness'] == 1
        assert 'Beast' in token['subtypes']


# ============================================================
# Test 12: Animal Companion Random
# ============================================================

class TestAnimalCompanionRandom:
    """Animal Companion summons one of 3 random beasts (Huffer/Leokk/Misha)."""

    def test_animal_companion_summons_one_token(self):
        """Animal Companion should produce exactly 1 CREATE_TOKEN event."""
        game, p1, p2 = new_hs_game()
        random.seed(0)

        ac_obj = game.create_object(
            name=ANIMAL_COMPANION.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=ANIMAL_COMPANION.characteristics, card_def=ANIMAL_COMPANION
        )
        events = ANIMAL_COMPANION.spell_effect(ac_obj, game.state, [])

        token_events = [e for e in events if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) == 1, (
            f"Animal Companion should create 1 token, got {len(token_events)}"
        )

    def test_animal_companion_all_three_possible(self):
        """All three companions (Huffer, Leokk, Misha) should be possible outcomes."""
        game, p1, p2 = new_hs_game()
        names_seen = set()

        for seed in range(100):
            random.seed(seed)
            ac_obj = game.create_object(
                name=ANIMAL_COMPANION.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
                characteristics=ANIMAL_COMPANION.characteristics, card_def=ANIMAL_COMPANION
            )
            events = ANIMAL_COMPANION.spell_effect(ac_obj, game.state, [])
            if events:
                token_name = events[0].payload['token']['name']
                names_seen.add(token_name)
            if len(names_seen) == 3:
                break

        assert 'Huffer' in names_seen, "Huffer should be a possible outcome"
        assert 'Leokk' in names_seen, "Leokk should be a possible outcome"
        assert 'Misha' in names_seen, "Misha should be a possible outcome"

    def test_animal_companion_huffer_has_charge(self):
        """Huffer (4/2) should have Charge."""
        game, p1, p2 = new_hs_game()
        # Find a seed that produces Huffer
        for seed in range(100):
            random.seed(seed)
            ac_obj = game.create_object(
                name=ANIMAL_COMPANION.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
                characteristics=ANIMAL_COMPANION.characteristics, card_def=ANIMAL_COMPANION
            )
            events = ANIMAL_COMPANION.spell_effect(ac_obj, game.state, [])
            if events and events[0].payload['token']['name'] == 'Huffer':
                token = events[0].payload['token']
                assert token['power'] == 4
                assert token['toughness'] == 2
                assert 'charge' in token.get('keywords', set()), (
                    "Huffer should have Charge"
                )
                return
        assert False, "Could not produce Huffer in 100 seeds"

    def test_animal_companion_misha_has_taunt(self):
        """Misha (4/4) should have Taunt."""
        game, p1, p2 = new_hs_game()
        for seed in range(100):
            random.seed(seed)
            ac_obj = game.create_object(
                name=ANIMAL_COMPANION.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
                characteristics=ANIMAL_COMPANION.characteristics, card_def=ANIMAL_COMPANION
            )
            events = ANIMAL_COMPANION.spell_effect(ac_obj, game.state, [])
            if events and events[0].payload['token']['name'] == 'Misha':
                token = events[0].payload['token']
                assert token['power'] == 4
                assert token['toughness'] == 4
                assert 'taunt' in token.get('keywords', set()), (
                    "Misha should have Taunt"
                )
                return
        assert False, "Could not produce Misha in 100 seeds"

    def test_animal_companion_all_are_beasts(self):
        """All companions should be Beasts."""
        game, p1, p2 = new_hs_game()
        for seed in range(30):
            random.seed(seed)
            ac_obj = game.create_object(
                name=ANIMAL_COMPANION.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
                characteristics=ANIMAL_COMPANION.characteristics, card_def=ANIMAL_COMPANION
            )
            events = ANIMAL_COMPANION.spell_effect(ac_obj, game.state, [])
            if events:
                token = events[0].payload['token']
                assert 'Beast' in token['subtypes'], (
                    f"{token['name']} should be a Beast"
                )


# ============================================================
# Test 13: Timber Wolf Beast Aura
# ============================================================

class TestTimberWolfBeastAura:
    """Timber Wolf gives all friendly beasts +1 Attack."""

    def test_timber_wolf_boosts_friendly_beast(self):
        """Timber Wolf on board should give another friendly Beast +1 attack via QUERY."""
        game, p1, p2 = new_hs_game()
        raptor = make_obj(game, BLOODFEN_RAPTOR, p2)
        timber_wolf = make_obj(game, TIMBER_WOLF, p2)

        # Bloodfen Raptor is a 3/2 Beast; with Timber Wolf aura should be 4/2
        effective_power = get_power(raptor, game.state)
        assert effective_power == 4, (
            f"Raptor should have 4 attack with Timber Wolf aura (3+1), got {effective_power}"
        )

    def test_timber_wolf_does_not_boost_self(self):
        """Timber Wolf should NOT boost its own attack."""
        game, p1, p2 = new_hs_game()
        timber_wolf = make_obj(game, TIMBER_WOLF, p2)

        effective_power = get_power(timber_wolf, game.state)
        assert effective_power == 1, (
            f"Timber Wolf should have 1 attack (no self-boost), got {effective_power}"
        )

    def test_timber_wolf_does_not_boost_non_beast(self):
        """Timber Wolf should NOT boost non-Beast minions."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        timber_wolf = make_obj(game, TIMBER_WOLF, p2)

        effective_power = get_power(yeti, game.state)
        assert effective_power == 4, (
            f"Yeti (non-Beast) should remain at 4 attack with Timber Wolf, got {effective_power}"
        )

    def test_timber_wolf_does_not_boost_enemy_beast(self):
        """Timber Wolf should NOT boost enemy Beasts."""
        game, p1, p2 = new_hs_game()
        enemy_raptor = make_obj(game, BLOODFEN_RAPTOR, p1)
        timber_wolf = make_obj(game, TIMBER_WOLF, p2)

        effective_power = get_power(enemy_raptor, game.state)
        assert effective_power == 3, (
            f"Enemy Raptor should remain at 3 attack, got {effective_power}"
        )


# ============================================================
# Test 14: Starving Buzzard Draw on Beast
# ============================================================

class TestStarvingBuzzardDrawOnBeast:
    """Starving Buzzard draws a card when you summon a Beast."""

    def test_buzzard_setup_creates_interceptor(self):
        """Starving Buzzard should register a REACT interceptor for Beast summoning."""
        game, p1, p2 = new_hs_game()
        buzzard = make_obj(game, STARVING_BUZZARD, p2)

        # Check that interceptors were registered
        buzzard_interceptors = [
            i for i in game.state.interceptors.values()
            if i.source == buzzard.id
        ]
        assert len(buzzard_interceptors) >= 1, (
            "Starving Buzzard should register at least 1 interceptor"
        )

    def test_buzzard_is_3_2_beast(self):
        """Starving Buzzard should be a 3/2 Beast."""
        game, p1, p2 = new_hs_game()
        buzzard = make_obj(game, STARVING_BUZZARD, p2)
        assert buzzard.characteristics.power == 3
        assert buzzard.characteristics.toughness == 2
        assert 'Beast' in buzzard.characteristics.subtypes


# ============================================================
# Test 15: Multi-Shot
# ============================================================

class TestMultiShot:
    """Multi-Shot deals 3 damage to 2 random enemy minions."""

    def test_multi_shot_hits_2_enemies(self):
        """With 3 enemy minions, Multi-Shot should hit exactly 2."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wisp2 = make_obj(game, WISP, p1)
        wisp3 = make_obj(game, WISP, p1)
        random.seed(0)

        ms_obj = game.create_object(
            name=MULTI_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MULTI_SHOT.characteristics, card_def=MULTI_SHOT
        )
        events = MULTI_SHOT.spell_effect(ms_obj, game.state, [])

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        assert len(damage_events) == 2, (
            f"Multi-Shot should deal damage to 2 targets, got {len(damage_events)}"
        )

    def test_multi_shot_deals_3_each(self):
        """Each Multi-Shot hit should deal 3 damage."""
        game, p1, p2 = new_hs_game()
        make_obj(game, WISP, p1)
        make_obj(game, WISP, p1)
        random.seed(0)

        ms_obj = game.create_object(
            name=MULTI_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MULTI_SHOT.characteristics, card_def=MULTI_SHOT
        )
        events = MULTI_SHOT.spell_effect(ms_obj, game.state, [])

        for e in events:
            if e.type == EventType.DAMAGE:
                assert e.payload['amount'] == 3, (
                    f"Multi-Shot damage should be 3, got {e.payload['amount']}"
                )

    def test_multi_shot_with_1_enemy(self):
        """With only 1 enemy minion, Multi-Shot hits only 1."""
        game, p1, p2 = new_hs_game()
        wisp = make_obj(game, WISP, p1)

        ms_obj = game.create_object(
            name=MULTI_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MULTI_SHOT.characteristics, card_def=MULTI_SHOT
        )
        events = MULTI_SHOT.spell_effect(ms_obj, game.state, [])

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        assert len(damage_events) == 1, (
            f"Multi-Shot with 1 enemy should hit 1, got {len(damage_events)}"
        )
        assert damage_events[0].payload['target'] == wisp.id

    def test_multi_shot_with_0_enemies(self):
        """With no enemy minions, Multi-Shot does nothing."""
        game, p1, p2 = new_hs_game()

        ms_obj = game.create_object(
            name=MULTI_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MULTI_SHOT.characteristics, card_def=MULTI_SHOT
        )
        events = MULTI_SHOT.spell_effect(ms_obj, game.state, [])

        assert len(events) == 0, (
            f"Multi-Shot with no enemies should produce 0 events, got {len(events)}"
        )

    def test_multi_shot_hits_different_targets(self):
        """Multi-Shot should hit 2 distinct targets."""
        game, p1, p2 = new_hs_game()
        wisp1 = make_obj(game, WISP, p1)
        wisp2 = make_obj(game, WISP, p1)
        random.seed(0)

        ms_obj = game.create_object(
            name=MULTI_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=MULTI_SHOT.characteristics, card_def=MULTI_SHOT
        )
        events = MULTI_SHOT.spell_effect(ms_obj, game.state, [])

        damage_events = [e for e in events if e.type == EventType.DAMAGE]
        targets = [e.payload['target'] for e in damage_events]
        assert len(set(targets)) == 2, (
            f"Multi-Shot should hit 2 distinct targets, got targets: {targets}"
        )


# ============================================================
# Test 16: Arcane Shot
# ============================================================

class TestArcaneShot:
    """Arcane Shot deals 2 damage to any target."""

    def test_arcane_shot_deals_2_damage(self):
        """Arcane Shot should deal exactly 2 damage to the target."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)

        as_obj = game.create_object(
            name=ARCANE_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=ARCANE_SHOT.characteristics, card_def=ARCANE_SHOT
        )
        events = ARCANE_SHOT.spell_effect(as_obj, game.state, [yeti.id])

        assert len(events) == 1
        assert events[0].type == EventType.DAMAGE
        assert events[0].payload['amount'] == 2
        assert events[0].payload['target'] == yeti.id

    def test_arcane_shot_can_target_hero(self):
        """Arcane Shot should be able to target a hero."""
        game, p1, p2 = new_hs_game()

        as_obj = game.create_object(
            name=ARCANE_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=ARCANE_SHOT.characteristics, card_def=ARCANE_SHOT
        )
        events = ARCANE_SHOT.spell_effect(as_obj, game.state, [p1.hero_id])

        assert len(events) == 1
        assert events[0].payload['target'] == p1.hero_id
        assert events[0].payload['amount'] == 2

    def test_arcane_shot_no_target_no_events(self):
        """Arcane Shot with no target produces no events."""
        game, p1, p2 = new_hs_game()

        as_obj = game.create_object(
            name=ARCANE_SHOT.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=ARCANE_SHOT.characteristics, card_def=ARCANE_SHOT
        )
        events = ARCANE_SHOT.spell_effect(as_obj, game.state, [])

        assert len(events) == 0, (
            f"Arcane Shot with no target should produce 0 events, got {len(events)}"
        )


# ============================================================
# Test 17: Tracking
# ============================================================

class TestTracking:
    """Tracking (simplified) draws a card."""

    def test_tracking_produces_draw_event(self):
        """Tracking should produce a DRAW event."""
        game, p1, p2 = new_hs_game()

        tr_obj = game.create_object(
            name=TRACKING.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=TRACKING.characteristics, card_def=TRACKING
        )
        events = TRACKING.spell_effect(tr_obj, game.state, [])

        assert len(events) == 1
        assert events[0].type == EventType.DRAW
        assert events[0].payload['player'] == p2.id

    def test_tracking_draw_count_is_1(self):
        """Tracking draw event should have count=1."""
        game, p1, p2 = new_hs_game()

        tr_obj = game.create_object(
            name=TRACKING.name, owner_id=p2.id, zone=ZoneType.BATTLEFIELD,
            characteristics=TRACKING.characteristics, card_def=TRACKING
        )
        events = TRACKING.spell_effect(tr_obj, game.state, [])

        assert events[0].payload.get('count') == 1, (
            f"Tracking should draw 1 card, got count={events[0].payload.get('count')}"
        )
