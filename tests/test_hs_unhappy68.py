"""
Hearthstone Unhappy Path Tests - Batch 68

Draw triggers and card generation: Northshire Cleric draw on heal,
Gadgetzan Auctioneer draw on spell, Azure Drake battlecry draw, Loot
Hoarder deathrattle draw, Novice Engineer battlecry draw, Gnomish
Inventor battlecry draw, Sprint draw 4, Arcane Intellect draw 2,
Nourish draw 3, Lay on Hands draw 3, Battle Rage draw per damaged
friendly, Commanding Shout draw, Divine Favor draw to match opponent,
Cult Master draw on friendly minion death, card generation from Ysera,
Thoughtsteal copy from opponent deck, Mind Vision copy from opponent hand.
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
    GNOMISH_INVENTOR,
)
from src.cards.hearthstone.classic import (
    NOVICE_ENGINEER, LOOT_HOARDER, AZURE_DRAKE, CULT_MASTER,
    GADGETZAN_AUCTIONEER, ARCANE_INTELLECT, SPRINT,
)
from src.cards.hearthstone.priest import (
    NORTHSHIRE_CLERIC, MIND_VISION, THOUGHTSTEAL,
)
from src.cards.hearthstone.warrior import BATTLE_RAGE
from src.cards.hearthstone.paladin import DIVINE_FAVOR, LAY_ON_HANDS
from src.cards.hearthstone.druid import NOURISH


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game():
    """Create a fresh Hearthstone game with 2 players, heroes, and 10 mana each."""
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Warrior"], HERO_POWERS["Warrior"])
    game.setup_hearthstone_player(p2, HEROES["Mage"], HERO_POWERS["Mage"])
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
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    return obj


def play_from_hand(game, card_def, owner):
    """Simulate playing a minion from hand (triggers battlecry via ZONE_CHANGE)."""
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


def get_hand_objects(game, player):
    """Get all objects in a player's hand."""
    hand_key = f"hand_{player.id}"
    hand = game.state.zones.get(hand_key)
    if not hand:
        return []
    return [game.state.objects[oid] for oid in hand.objects if oid in game.state.objects]


def add_cards_to_library(game, player, card_def, count):
    """Add card objects to a player's library for draw testing."""
    for _ in range(count):
        game.create_object(
            name=card_def.name, owner_id=player.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


def get_hand_size(game, player):
    """Get number of cards in a player's hand."""
    hand_key = f"hand_{player.id}"
    hand = game.state.zones.get(hand_key)
    return len(hand.objects) if hand else 0


def get_library_size(game, player):
    """Get number of cards in a player's library."""
    lib_key = f"library_{player.id}"
    lib = game.state.zones.get(lib_key)
    return len(lib.objects) if lib else 0


# ============================================================
# Test 1: TestNorthshireClericDrawOnHeal
# ============================================================

class TestNorthshireClericDrawOnHeal:
    def test_heal_one_minion_draws_one(self):
        """Northshire Cleric triggers a draw when any minion is healed."""
        game, p1, p2 = new_hs_game()
        cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)

        # Create a damaged minion
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        yeti.state.damage = 2

        add_cards_to_library(game, p1, WISP, 5)
        hand_before = get_hand_size(game, p1)

        # Heal the yeti (LIFE_CHANGE with object_id and positive amount)
        heal_amount = min(yeti.state.damage, 2)
        yeti.state.damage -= heal_amount
        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'object_id': yeti.id, 'amount': heal_amount},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 1, (
            f"Northshire Cleric should draw 1 card when a minion is healed, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_heal_two_minions_draws_two(self):
        """Healing 2 minions should trigger 2 separate draws from Northshire Cleric."""
        game, p1, p2 = new_hs_game()
        cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)

        # Create 2 damaged minions
        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m1.state.damage = 2
        m2 = make_obj(game, BLOODFEN_RAPTOR, p2)
        m2.state.damage = 1

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        # Heal minion 1
        heal1 = min(m1.state.damage, 2)
        m1.state.damage -= heal1
        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'object_id': m1.id, 'amount': heal1},
            source='test'
        ))

        # Heal minion 2
        heal2 = min(m2.state.damage, 1)
        m2.state.damage -= heal2
        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'object_id': m2.id, 'amount': heal2},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 2, (
            f"Healing 2 minions should draw 2 cards via Northshire, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_heal_at_full_health_does_not_draw(self):
        """Healing a minion at full health (amount 0) should NOT trigger Northshire."""
        game, p1, p2 = new_hs_game()
        cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        # Yeti has no damage, so healing does nothing

        add_cards_to_library(game, p1, WISP, 5)
        hand_before = get_hand_size(game, p1)

        # Emit LIFE_CHANGE with amount=0 (no actual healing)
        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'object_id': yeti.id, 'amount': 0},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before, (
            f"Healing 0 should not trigger Northshire Cleric draw, "
            f"hand went from {hand_before} to {hand_after}"
        )


# ============================================================
# Test 2: TestGadgetzanAuctioneerDrawOnSpell
# ============================================================

class TestGadgetzanAuctioneerDrawOnSpell:
    def test_cast_one_spell_draws_one(self):
        """Gadgetzan Auctioneer draws 1 card when you cast a spell."""
        game, p1, p2 = new_hs_game()
        auctioneer = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        # Cast Arcane Intellect (draws 2 by itself + 1 from Auctioneer = 3 total)
        cast_spell(game, ARCANE_INTELLECT, p1)

        hand_after = get_hand_size(game, p1)
        # Arcane Intellect draws 2 (two individual DRAW events of count 1 each)
        # Plus Auctioneer draws 1 on SPELL_CAST
        assert hand_after == hand_before + 3, (
            f"Arcane Intellect (2 draws) + Auctioneer (1 draw) = 3 total, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_cast_two_spells_draws_two_from_auctioneer(self):
        """Casting 2 spells with Auctioneer should draw 2 from Auctioneer."""
        game, p1, p2 = new_hs_game()
        auctioneer = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        add_cards_to_library(game, p1, WISP, 20)
        hand_before = get_hand_size(game, p1)

        # Cast 2 spells. Use Arcane Intellect (draws 2) twice
        cast_spell(game, ARCANE_INTELLECT, p1)
        cast_spell(game, ARCANE_INTELLECT, p1)

        hand_after = get_hand_size(game, p1)
        # 2x Arcane Intellect = 4 draws + 2x Auctioneer triggers = 2 draws = 6 total
        assert hand_after == hand_before + 6, (
            f"Two Arcane Intellects (4 draws) + 2 Auctioneer triggers (2 draws) = 6, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_opponent_spell_does_not_trigger_auctioneer(self):
        """Opponent casting a spell should NOT trigger your Auctioneer."""
        game, p1, p2 = new_hs_game()
        auctioneer = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        add_cards_to_library(game, p1, WISP, 10)
        add_cards_to_library(game, p2, WISP, 10)
        hand_before = get_hand_size(game, p1)

        # Opponent casts a spell
        cast_spell(game, ARCANE_INTELLECT, p2)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before, (
            f"Opponent's spell should not trigger your Auctioneer, "
            f"p1 hand went from {hand_before} to {hand_after}"
        )


# ============================================================
# Test 3: TestCultMasterDrawOnFriendlyDeath
# ============================================================

class TestCultMasterDrawOnFriendlyDeath:
    def test_friendly_minion_death_draws(self):
        """Cult Master draws a card when a friendly minion dies."""
        game, p1, p2 = new_hs_game()
        cult_master = make_obj(game, CULT_MASTER, p1)
        wisp = make_obj(game, WISP, p1)

        add_cards_to_library(game, p1, CHILLWIND_YETI, 5)
        hand_before = get_hand_size(game, p1)

        # Kill the wisp
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': wisp.id, 'reason': 'combat'},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 1, (
            f"Cult Master should draw 1 card when a friendly minion dies, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_enemy_minion_death_does_not_draw(self):
        """Cult Master should NOT draw when an enemy minion dies."""
        game, p1, p2 = new_hs_game()
        cult_master = make_obj(game, CULT_MASTER, p1)
        enemy_minion = make_obj(game, WISP, p2)

        add_cards_to_library(game, p1, CHILLWIND_YETI, 5)
        hand_before = get_hand_size(game, p1)

        # Kill enemy minion
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': enemy_minion.id, 'reason': 'combat'},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before, (
            f"Cult Master should not draw when enemy minion dies, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_cult_master_self_death_does_not_draw(self):
        """Cult Master dying should NOT trigger its own draw."""
        game, p1, p2 = new_hs_game()
        cult_master = make_obj(game, CULT_MASTER, p1)

        add_cards_to_library(game, p1, CHILLWIND_YETI, 5)
        hand_before = get_hand_size(game, p1)

        # Kill Cult Master itself
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cult_master.id, 'reason': 'combat'},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before, (
            f"Cult Master dying should not trigger its own draw, "
            f"hand went from {hand_before} to {hand_after}"
        )


# ============================================================
# Test 4: TestAzureDrakeDrawsBattlecry
# ============================================================

class TestAzureDrakeDrawsBattlecry:
    def test_azure_drake_battlecry_draws_1(self):
        """Azure Drake battlecry draws exactly 1 card."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p1, WISP, 5)
        hand_before = get_hand_size(game, p1)

        drake = make_obj(game, AZURE_DRAKE, p1)
        events = AZURE_DRAKE.battlecry(drake, game.state)
        for e in events:
            game.emit(e)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 1, (
            f"Azure Drake battlecry should draw 1 card, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_azure_drake_battlecry_emits_draw_event(self):
        """Azure Drake battlecry returns a DRAW event with count 1."""
        game, p1, p2 = new_hs_game()
        drake = make_obj(game, AZURE_DRAKE, p1)
        events = AZURE_DRAKE.battlecry(drake, game.state)

        assert len(events) == 1, f"Expected 1 event from battlecry, got {len(events)}"
        assert events[0].type == EventType.DRAW
        assert events[0].payload.get('count') == 1
        assert events[0].payload.get('player') == p1.id


# ============================================================
# Test 5: TestNoviceEngineerDraw
# ============================================================

class TestNoviceEngineerDraw:
    def test_novice_engineer_battlecry_draws_1(self):
        """Novice Engineer battlecry draws exactly 1 card."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p1, WISP, 5)
        hand_before = get_hand_size(game, p1)

        novice = make_obj(game, NOVICE_ENGINEER, p1)
        events = NOVICE_ENGINEER.battlecry(novice, game.state)
        for e in events:
            game.emit(e)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 1, (
            f"Novice Engineer battlecry should draw 1 card, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_novice_engineer_event_is_draw(self):
        """Novice Engineer battlecry returns exactly 1 DRAW event."""
        game, p1, p2 = new_hs_game()
        novice = make_obj(game, NOVICE_ENGINEER, p1)
        events = NOVICE_ENGINEER.battlecry(novice, game.state)

        assert len(events) == 1
        assert events[0].type == EventType.DRAW
        assert events[0].payload.get('count') == 1


# ============================================================
# Test 6: TestGnomishInventorDraw
# ============================================================

class TestGnomishInventorDraw:
    def test_gnomish_inventor_battlecry_draws_1(self):
        """Gnomish Inventor battlecry draws exactly 1 card."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p1, WISP, 5)
        hand_before = get_hand_size(game, p1)

        inventor = make_obj(game, GNOMISH_INVENTOR, p1)
        events = GNOMISH_INVENTOR.battlecry(inventor, game.state)
        for e in events:
            game.emit(e)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 1, (
            f"Gnomish Inventor battlecry should draw 1 card, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_gnomish_inventor_event_is_draw(self):
        """Gnomish Inventor battlecry returns exactly 1 DRAW event."""
        game, p1, p2 = new_hs_game()
        inventor = make_obj(game, GNOMISH_INVENTOR, p1)
        events = GNOMISH_INVENTOR.battlecry(inventor, game.state)

        assert len(events) == 1
        assert events[0].type == EventType.DRAW
        assert events[0].payload.get('count') == 1


# ============================================================
# Test 7: TestArcaneIntellectDraw2
# ============================================================

class TestArcaneIntellectDraw2:
    def test_arcane_intellect_draws_2(self):
        """Arcane Intellect draws exactly 2 cards."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, ARCANE_INTELLECT, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 2, (
            f"Arcane Intellect should draw 2 cards, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_arcane_intellect_emits_two_draw_events(self):
        """Arcane Intellect produces 2 separate DRAW events (each with count 1)."""
        game, p1, p2 = new_hs_game()
        obj = make_obj(game, ARCANE_INTELLECT, p1)
        events = ARCANE_INTELLECT.spell_effect(obj, game.state, [])

        assert len(events) == 2, (
            f"Arcane Intellect should emit 2 DRAW events, got {len(events)}"
        )
        for e in events:
            assert e.type == EventType.DRAW
            assert e.payload.get('count') == 1


# ============================================================
# Test 8: TestSprintDraw4
# ============================================================

class TestSprintDraw4:
    def test_sprint_draws_4(self):
        """Sprint draws exactly 4 cards."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, SPRINT, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 4, (
            f"Sprint should draw 4 cards, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_sprint_emits_single_draw_event_count_4(self):
        """Sprint produces 1 DRAW event with count=4."""
        game, p1, p2 = new_hs_game()
        obj = make_obj(game, SPRINT, p1)
        events = SPRINT.spell_effect(obj, game.state, [])

        assert len(events) == 1, (
            f"Sprint should emit 1 DRAW event, got {len(events)}"
        )
        assert events[0].type == EventType.DRAW
        assert events[0].payload.get('count') == 4


# ============================================================
# Test 9: TestNourishDraw3
# ============================================================

class TestNourishDraw3:
    def test_nourish_draw_mode_draws_3(self):
        """Nourish (draw mode) draws exactly 3 cards when player has >= 8 mana crystals."""
        game, p1, p2 = new_hs_game()
        # Player has 10 mana crystals (>= 8), so Nourish picks draw mode
        assert p1.mana_crystals >= 8, (
            f"Test setup requires >= 8 mana crystals, got {p1.mana_crystals}"
        )

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, NOURISH, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 3, (
            f"Nourish (draw mode) should draw 3 cards, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_nourish_ramp_mode_when_low_mana(self):
        """Nourish ramps when player has < 8 mana crystals (does not draw)."""
        game, p1, p2 = new_hs_game()
        # Set mana crystals below 8 so Nourish picks ramp mode
        p1.mana_crystals = 5
        p1.mana_crystals_available = 5

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)
        mana_before = p1.mana_crystals

        cast_spell(game, NOURISH, p1)

        hand_after = get_hand_size(game, p1)
        mana_after = p1.mana_crystals

        assert hand_after == hand_before, (
            f"Nourish ramp mode should not draw cards, "
            f"hand went from {hand_before} to {hand_after}"
        )
        assert mana_after == mana_before + 2, (
            f"Nourish ramp mode should add 2 mana crystals, "
            f"went from {mana_before} to {mana_after}"
        )


# ============================================================
# Test 10: TestLayOnHandsDraw3
# ============================================================

class TestLayOnHandsDraw3:
    def test_lay_on_hands_draws_3(self):
        """Lay on Hands draws exactly 3 cards."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, LAY_ON_HANDS, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 3, (
            f"Lay on Hands should draw 3 cards, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_lay_on_hands_heals_8(self):
        """Lay on Hands heals 8 health to the controlling player."""
        game, p1, p2 = new_hs_game()
        p1.life = 15  # Damaged hero

        add_cards_to_library(game, p1, WISP, 10)

        cast_spell(game, LAY_ON_HANDS, p1)

        assert p1.life == 23, (
            f"Lay on Hands should heal 8 (15 + 8 = 23), got {p1.life}"
        )

    def test_lay_on_hands_heals_and_draws_simultaneously(self):
        """Lay on Hands emits both a LIFE_CHANGE (+8) and a DRAW (count 3) event."""
        game, p1, p2 = new_hs_game()
        obj = make_obj(game, LAY_ON_HANDS, p1)
        events = LAY_ON_HANDS.spell_effect(obj, game.state, [])

        assert len(events) == 2, f"Expected 2 events, got {len(events)}"

        life_events = [e for e in events if e.type == EventType.LIFE_CHANGE]
        draw_events = [e for e in events if e.type == EventType.DRAW]

        assert len(life_events) == 1, "Should have 1 LIFE_CHANGE event"
        assert life_events[0].payload.get('amount') == 8
        assert len(draw_events) == 1, "Should have 1 DRAW event"
        assert draw_events[0].payload.get('count') == 3


# ============================================================
# Test 11: TestBattleRageDrawPerDamaged
# ============================================================

class TestBattleRageDrawPerDamaged:
    def test_draws_per_damaged_minion(self):
        """Battle Rage draws 1 card per damaged friendly minion."""
        game, p1, p2 = new_hs_game()

        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m1.state.damage = 1
        m2 = make_obj(game, BOULDERFIST_OGRE, p1)
        m2.state.damage = 3
        m3 = make_obj(game, WISP, p1)  # Undamaged

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, BATTLE_RAGE, p1)

        hand_after = get_hand_size(game, p1)
        # 2 damaged minions + hero at full health = 2 draws
        assert hand_after == hand_before + 2, (
            f"Battle Rage should draw 2 (2 damaged minions, hero full), "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_damaged_hero_counts(self):
        """Battle Rage counts a damaged hero as a friendly character."""
        game, p1, p2 = new_hs_game()
        p1.life = 25  # Hero is damaged (below max_life=30)

        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m1.state.damage = 2

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, BATTLE_RAGE, p1)

        hand_after = get_hand_size(game, p1)
        # 1 damaged minion + 1 damaged hero = 2 draws
        assert hand_after == hand_before + 2, (
            f"Battle Rage should draw 2 (1 damaged minion + damaged hero), "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_no_damaged_characters_draws_zero(self):
        """Battle Rage with no damaged characters draws nothing."""
        game, p1, p2 = new_hs_game()

        m1 = make_obj(game, CHILLWIND_YETI, p1)  # Undamaged

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, BATTLE_RAGE, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before, (
            f"Battle Rage should draw 0 with no damaged characters, "
            f"hand went from {hand_before} to {hand_after}"
        )


# ============================================================
# Test 12: TestDivineFavorDrawToMatch
# ============================================================

class TestDivineFavorDrawToMatch:
    def test_draws_to_match_opponent_hand(self):
        """Divine Favor draws until hand matches opponent's hand size."""
        game, p1, p2 = new_hs_game()

        # Give opponent 5 cards in hand
        for _ in range(5):
            make_obj(game, WISP, p2, zone=ZoneType.HAND)

        # p1 starts with 0 cards in hand
        p1_hand_before = get_hand_size(game, p1)
        p2_hand_size = get_hand_size(game, p2)
        assert p1_hand_before == 0, f"p1 should start with 0 cards, got {p1_hand_before}"
        assert p2_hand_size == 5, f"p2 should have 5 cards, got {p2_hand_size}"

        add_cards_to_library(game, p1, WISP, 10)

        cast_spell(game, DIVINE_FAVOR, p1)

        p1_hand_after = get_hand_size(game, p1)
        assert p1_hand_after == 5, (
            f"Divine Favor should draw until p1 has {p2_hand_size} cards, "
            f"p1 hand is now {p1_hand_after}"
        )

    def test_does_not_draw_if_hand_already_bigger(self):
        """Divine Favor draws nothing if your hand is already >= opponent's."""
        game, p1, p2 = new_hs_game()

        # Give p1 more cards than p2
        for _ in range(4):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)
        for _ in range(2):
            make_obj(game, WISP, p2, zone=ZoneType.HAND)

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, DIVINE_FAVOR, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before, (
            f"Divine Favor should draw 0 when already ahead, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_draws_exact_difference(self):
        """Divine Favor draws exactly the difference between hands."""
        game, p1, p2 = new_hs_game()

        # p1 has 2, p2 has 6 -> draw 4
        for _ in range(2):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)
        for _ in range(6):
            make_obj(game, WISP, p2, zone=ZoneType.HAND)

        add_cards_to_library(game, p1, WISP, 10)
        hand_before = get_hand_size(game, p1)

        cast_spell(game, DIVINE_FAVOR, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 4, (
            f"Divine Favor should draw 4 (6 - 2), "
            f"hand went from {hand_before} to {hand_after}"
        )


# ============================================================
# Test 13: TestThoughtstealCopies2
# ============================================================

class TestThoughtstealCopies2:
    def test_thoughtsteal_copies_2_from_opponent_deck(self):
        """Thoughtsteal copies 2 cards from opponent's deck into your hand."""
        game, p1, p2 = new_hs_game()

        # Put cards in opponent's library
        add_cards_to_library(game, p2, CHILLWIND_YETI, 5)

        hand_before = get_hand_size(game, p1)
        lib_before = get_library_size(game, p2)

        random.seed(42)
        cast_spell(game, THOUGHTSTEAL, p1)

        hand_after = get_hand_size(game, p1)
        lib_after = get_library_size(game, p2)

        assert hand_after == hand_before + 2, (
            f"Thoughtsteal should add 2 cards to hand, "
            f"hand went from {hand_before} to {hand_after}"
        )
        # Thoughtsteal copies without removing from opponent deck
        assert lib_after == lib_before, (
            f"Thoughtsteal should not remove cards from opponent's deck, "
            f"library went from {lib_before} to {lib_after}"
        )

    def test_thoughtsteal_from_1_card_deck_copies_1(self):
        """Thoughtsteal copies only 1 card if opponent has only 1 card in deck."""
        game, p1, p2 = new_hs_game()

        add_cards_to_library(game, p2, CHILLWIND_YETI, 1)

        hand_before = get_hand_size(game, p1)

        random.seed(42)
        cast_spell(game, THOUGHTSTEAL, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before + 1, (
            f"Thoughtsteal from 1-card deck should add 1 card, "
            f"hand went from {hand_before} to {hand_after}"
        )

    def test_thoughtsteal_from_empty_deck_copies_0(self):
        """Thoughtsteal from empty deck copies nothing."""
        game, p1, p2 = new_hs_game()

        # Ensure opponent's library is empty
        lib_key = f"library_{p2.id}"
        lib = game.state.zones.get(lib_key)
        if lib:
            lib.objects.clear()

        hand_before = get_hand_size(game, p1)

        cast_spell(game, THOUGHTSTEAL, p1)

        hand_after = get_hand_size(game, p1)
        assert hand_after == hand_before, (
            f"Thoughtsteal from empty deck should add 0 cards, "
            f"hand went from {hand_before} to {hand_after}"
        )


# ============================================================
# Test 14: TestMindVisionCopies1
# ============================================================

class TestMindVisionCopies1:
    def test_mind_vision_copies_1_from_opponent_hand(self):
        """Mind Vision copies 1 card from opponent's hand into your hand."""
        game, p1, p2 = new_hs_game()

        # Put cards in opponent's hand
        for _ in range(3):
            make_obj(game, CHILLWIND_YETI, p2, zone=ZoneType.HAND)

        p1_hand_before = get_hand_size(game, p1)
        p2_hand_before = get_hand_size(game, p2)

        random.seed(42)
        cast_spell(game, MIND_VISION, p1)

        p1_hand_after = get_hand_size(game, p1)
        p2_hand_after = get_hand_size(game, p2)

        assert p1_hand_after == p1_hand_before + 1, (
            f"Mind Vision should add 1 card to p1's hand, "
            f"hand went from {p1_hand_before} to {p1_hand_after}"
        )
        # Mind Vision copies, does not steal
        assert p2_hand_after == p2_hand_before, (
            f"Mind Vision should not remove cards from opponent's hand, "
            f"p2 hand went from {p2_hand_before} to {p2_hand_after}"
        )

    def test_mind_vision_from_empty_hand_copies_nothing(self):
        """Mind Vision from opponent with empty hand copies nothing."""
        game, p1, p2 = new_hs_game()

        # Ensure opponent hand is empty
        hand_key = f"hand_{p2.id}"
        hand = game.state.zones.get(hand_key)
        if hand:
            hand.objects.clear()

        p1_hand_before = get_hand_size(game, p1)

        cast_spell(game, MIND_VISION, p1)

        p1_hand_after = get_hand_size(game, p1)
        assert p1_hand_after == p1_hand_before, (
            f"Mind Vision from empty hand should copy nothing, "
            f"hand went from {p1_hand_before} to {p1_hand_after}"
        )


# ============================================================
# Test 15: TestDrawFromEmptyDeckFatigue
# ============================================================

class TestDrawFromEmptyDeckFatigue:
    def test_fatigue_damage_on_empty_deck(self):
        """Drawing from an empty deck deals fatigue damage to the hero."""
        game, p1, p2 = new_hs_game()

        # Ensure library is empty
        lib_key = f"library_{p1.id}"
        lib = game.state.zones.get(lib_key)
        if lib:
            lib.objects.clear()

        initial_life = p1.life
        p1.fatigue_damage = 0

        # Draw from empty deck
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        assert p1.fatigue_damage == 1, (
            f"Fatigue counter should be 1 after first empty draw, got {p1.fatigue_damage}"
        )
        assert p1.life == initial_life - 1, (
            f"Hero should take 1 fatigue damage (first draw), "
            f"expected {initial_life - 1}, got {p1.life}"
        )

    def test_fatigue_damage_increases(self):
        """Each subsequent draw from empty deck deals increasing fatigue damage."""
        game, p1, p2 = new_hs_game()

        lib_key = f"library_{p1.id}"
        lib = game.state.zones.get(lib_key)
        if lib:
            lib.objects.clear()

        initial_life = p1.life
        p1.fatigue_damage = 0

        # First empty draw: 1 damage
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))
        assert p1.life == initial_life - 1

        # Second empty draw: 2 damage (total 3)
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))
        assert p1.fatigue_damage == 2
        assert p1.life == initial_life - 3, (
            f"After 2 fatigue draws, hero should lose 1+2=3 life, "
            f"expected {initial_life - 3}, got {p1.life}"
        )

    def test_multi_draw_from_empty_deck(self):
        """Drawing multiple cards from empty deck triggers fatigue for each."""
        game, p1, p2 = new_hs_game()

        lib_key = f"library_{p1.id}"
        lib = game.state.zones.get(lib_key)
        if lib:
            lib.objects.clear()

        initial_life = p1.life
        p1.fatigue_damage = 0

        # Draw 3 from empty deck: 1 + 2 + 3 = 6 fatigue damage
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 3},
            source='test'
        ))

        assert p1.fatigue_damage == 3, (
            f"Fatigue counter should be 3 after 3 empty draws, got {p1.fatigue_damage}"
        )
        assert p1.life == initial_life - 6, (
            f"Hero should take 1+2+3=6 fatigue damage, "
            f"expected {initial_life - 6}, got {p1.life}"
        )


# ============================================================
# Test 16: TestOverdrawBurnsCard
# ============================================================

class TestOverdrawBurnsCard:
    def test_overdraw_at_10_cards_burns(self):
        """Drawing at 10 cards in hand burns the drawn card (not added to hand)."""
        game, p1, p2 = new_hs_game()

        # Fill hand to 10 cards
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        assert get_hand_size(game, p1) == 10, (
            f"Hand should be at 10, got {get_hand_size(game, p1)}"
        )

        # Put cards in library
        add_cards_to_library(game, p1, CHILLWIND_YETI, 3)
        lib_before = get_library_size(game, p1)

        # Try to draw
        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        lib_after = get_library_size(game, p1)

        assert hand_after == 10, (
            f"Hand should still be 10 after overdraw, got {hand_after}"
        )
        assert lib_after == lib_before - 1, (
            f"Library should lose 1 card (burned), "
            f"went from {lib_before} to {lib_after}"
        )

    def test_overdraw_sends_card_to_graveyard(self):
        """The burned card from overdraw goes to graveyard."""
        game, p1, p2 = new_hs_game()

        # Fill hand to 10
        for _ in range(10):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        # Add a specific card to library
        add_cards_to_library(game, p1, CHILLWIND_YETI, 1)

        graveyard_key = f"graveyard_{p1.id}"
        gy = game.state.zones.get(graveyard_key)
        gy_before = len(gy.objects) if gy else 0

        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        gy_after = len(gy.objects) if gy else 0
        assert gy_after == gy_before + 1, (
            f"Graveyard should gain 1 card from overdraw burn, "
            f"went from {gy_before} to {gy_after}"
        )

    def test_drawing_at_9_does_not_burn(self):
        """Drawing at 9 cards in hand should succeed (hand becomes 10)."""
        game, p1, p2 = new_hs_game()

        # Fill hand to 9
        for _ in range(9):
            make_obj(game, WISP, p1, zone=ZoneType.HAND)

        assert get_hand_size(game, p1) == 9

        add_cards_to_library(game, p1, CHILLWIND_YETI, 3)

        game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1.id, 'count': 1},
            source='test'
        ))

        hand_after = get_hand_size(game, p1)
        assert hand_after == 10, (
            f"Drawing at 9 should succeed, hand should be 10, got {hand_after}"
        )


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
