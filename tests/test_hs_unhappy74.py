"""
Hearthstone Unhappy Path Tests - Batch 74

Zone transitions and card lifecycle: card drawn from library to hand,
card played from hand to battlefield, minion death moves to graveyard,
spell cast moves to graveyard, bounce returns minion to hand,
bounce resets stats/damage/buffs, return to hand resets summoning
sickness, Sap returns enemy minion, Brewmaster returns friendly minion,
discard from hand to graveyard, transform replaces object in same zone,
zone counts track correctly after transitions.
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

from src.cards.hearthstone.basic import WISP, CHILLWIND_YETI, BOULDERFIST_OGRE
from src.cards.hearthstone.classic import (
    POLYMORPH, YOUTHFUL_BREWMASTER, ANCIENT_BREWMASTER,
)
from src.cards.hearthstone.rogue import SAP
from src.cards.hearthstone.mage import FIREBALL


# ============================================================
# Test Helpers
# ============================================================

def new_hs_game(p1_class="Mage", p2_class="Mage"):
    """Create a fresh Hearthstone game with configurable classes, 10 mana each."""
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


def play_minion(game, card_def, owner):
    """Play a minion from hand to battlefield (triggers ZONE_CHANGE)."""
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


def add_library_cards(game, owner, card_def, count):
    """Add cards to a player's library so draws don't fatigue."""
    for _ in range(count):
        game.create_object(
            name=card_def.name, owner_id=owner.id, zone=ZoneType.LIBRARY,
            characteristics=card_def.characteristics, card_def=card_def
        )


# ============================================================
# Test 1: Draw Moves Card from Library to Hand
# ============================================================

class TestDrawMovesCardToHand:
    def test_draw_moves_top_card_to_hand(self):
        """Drawing moves top card from library to hand. Library shrinks by 1."""
        game, p1, p2 = new_hs_game()

        # Add cards to library
        add_library_cards(game, p1, WISP, 5)

        library_key = f"library_{p1.id}"
        hand_key = f"hand_{p1.id}"

        lib_before = len(game.state.zones[library_key].objects)
        hand_before = len(game.state.zones[hand_key].objects)

        # The top card (first in list) should move
        top_card_id = game.state.zones[library_key].objects[0]

        game.draw_cards(p1.id, 1)

        lib_after = len(game.state.zones[library_key].objects)
        hand_after = len(game.state.zones[hand_key].objects)

        assert lib_after == lib_before - 1, (
            f"Library should shrink by 1: was {lib_before}, now {lib_after}"
        )
        assert hand_after == hand_before + 1, (
            f"Hand should grow by 1: was {hand_before}, now {hand_after}"
        )
        assert top_card_id in game.state.zones[hand_key].objects, (
            "The top card from library should now be in hand"
        )
        assert top_card_id not in game.state.zones[library_key].objects, (
            "The drawn card should no longer be in library"
        )


# ============================================================
# Test 2: Draw Sets Hand Zone
# ============================================================

class TestDrawSetsHandZone:
    def test_drawn_card_zone_is_hand(self):
        """After draw, card.zone == ZoneType.HAND."""
        game, p1, p2 = new_hs_game()

        add_library_cards(game, p1, WISP, 3)

        library_key = f"library_{p1.id}"
        top_card_id = game.state.zones[library_key].objects[0]

        game.draw_cards(p1.id, 1)

        obj = game.state.objects[top_card_id]
        assert obj.zone == ZoneType.HAND, (
            f"Drawn card zone should be HAND, got {obj.zone}"
        )


# ============================================================
# Test 3: Draw Multiple Cards
# ============================================================

class TestDrawMultipleCards:
    def test_draw_three_cards(self):
        """Draw 3 -> hand grows by 3, library shrinks by 3."""
        game, p1, p2 = new_hs_game()

        add_library_cards(game, p1, WISP, 10)

        library_key = f"library_{p1.id}"
        hand_key = f"hand_{p1.id}"

        lib_before = len(game.state.zones[library_key].objects)
        hand_before = len(game.state.zones[hand_key].objects)

        game.draw_cards(p1.id, 3)

        lib_after = len(game.state.zones[library_key].objects)
        hand_after = len(game.state.zones[hand_key].objects)

        assert lib_after == lib_before - 3, (
            f"Library should shrink by 3: was {lib_before}, now {lib_after}"
        )
        assert hand_after == hand_before + 3, (
            f"Hand should grow by 3: was {hand_before}, now {hand_after}"
        )


# ============================================================
# Test 4: Play Minion to Field
# ============================================================

class TestPlayMinionToField:
    def test_play_minion_moves_to_battlefield(self):
        """Playing a minion moves it from hand to battlefield."""
        game, p1, p2 = new_hs_game()

        obj = play_minion(game, CHILLWIND_YETI, p1)

        assert obj.zone == ZoneType.BATTLEFIELD, (
            f"Played minion should be on BATTLEFIELD, got {obj.zone}"
        )
        battlefield = game.state.zones.get('battlefield')
        assert obj.id in battlefield.objects, (
            "Played minion should be in battlefield zone list"
        )


# ============================================================
# Test 5: Played Minion Gets Summoning Sickness
# ============================================================

class TestPlayMinionGetsSummoningSickness:
    def test_played_minion_has_summoning_sickness(self):
        """Played minion has summoning_sickness = True."""
        game, p1, p2 = new_hs_game()

        obj = play_minion(game, CHILLWIND_YETI, p1)

        assert obj.state.summoning_sickness is True, (
            "Minion played to battlefield should have summoning sickness"
        )


# ============================================================
# Test 6: Spell Goes to Graveyard
# ============================================================

class TestSpellGoesToGraveyard:
    def test_spell_not_on_battlefield_after_cast(self):
        """After casting a spell, it should not remain on battlefield."""
        game, p1, p2 = new_hs_game()

        # Create a spell in hand, then cast it using our helper
        # cast_spell creates the object on battlefield temporarily, then
        # we verify no copy of the spell persists on battlefield as a minion.
        # In the test helper pattern, the spell object is created for its effect;
        # in a real game flow the spell would move to graveyard.
        # We test by using the DRAW event to emit Fireball, then checking zones.

        # Create fireball in hand
        fb = game.create_object(
            name=FIREBALL.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=FIREBALL.characteristics, card_def=FIREBALL
        )
        hand_key = f"hand_{p1.id}"
        assert fb.id in game.state.zones[hand_key].objects, (
            "Fireball should start in hand"
        )

        # Simulate casting: invoke spell effect, then move to graveyard
        events = FIREBALL.spell_effect(fb, game.state, [p2.hero_id])
        for e in events:
            game.emit(e)

        # Move spell to graveyard (as the game would do after resolution)
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': fb.id,
                'from_zone_type': ZoneType.HAND,
                'to_zone_type': ZoneType.GRAVEYARD,
            },
            source=fb.id
        ))

        graveyard_key = f"graveyard_{p1.id}"
        assert fb.zone == ZoneType.GRAVEYARD, (
            f"Spell should be in graveyard after cast, got {fb.zone}"
        )
        assert fb.id in game.state.zones[graveyard_key].objects, (
            "Spell should be in graveyard zone list"
        )
        assert fb.id not in game.state.zones[hand_key].objects, (
            "Spell should no longer be in hand"
        )


# ============================================================
# Test 7: Death Moves to Graveyard
# ============================================================

class TestDeathMovesToGraveyard:
    def test_dead_minion_goes_to_graveyard(self):
        """Dead minion is removed from battlefield, moved to graveyard."""
        game, p1, p2 = new_hs_game()

        wisp = make_obj(game, WISP, p1)

        battlefield = game.state.zones.get('battlefield')
        assert wisp.id in battlefield.objects, "Wisp should be on battlefield"

        # Destroy the minion
        game.destroy(wisp.id)

        graveyard_key = f"graveyard_{p1.id}"
        assert wisp.id not in battlefield.objects, (
            "Dead minion should be removed from battlefield"
        )
        assert wisp.zone == ZoneType.GRAVEYARD, (
            f"Dead minion zone should be GRAVEYARD, got {wisp.zone}"
        )
        assert wisp.id in game.state.zones[graveyard_key].objects, (
            "Dead minion should be in graveyard zone list"
        )


# ============================================================
# Test 8: Death Clears Interceptors
# ============================================================

class TestDeathClearsInterceptors:
    def test_dead_minion_interceptors_removed(self):
        """Dead minion's interceptors are removed from state after death."""
        game, p1, p2 = new_hs_game()

        # Youthful Brewmaster has a battlecry but no persistent interceptors.
        # Use a minion with setup_interceptors for this test.
        # We'll manually add an interceptor to verify cleanup.
        wisp = make_obj(game, WISP, p1)

        # Manually register an interceptor attached to the wisp
        interceptor = Interceptor(
            id=new_id(),
            source=wisp.id,
            controller=p1.id,
            priority=InterceptorPriority.REACT,
            filter=lambda e, s: False,
            handler=lambda e, s: InterceptorResult(action=InterceptorAction.PASS),
            duration='while_on_battlefield',
        )
        interceptor.timestamp = game.state.next_timestamp()
        game.state.interceptors[interceptor.id] = interceptor
        wisp.interceptor_ids.append(interceptor.id)

        int_id = interceptor.id
        assert int_id in game.state.interceptors, "Interceptor should be registered"

        # Destroy the minion
        game.destroy(wisp.id)

        assert int_id not in game.state.interceptors, (
            "Interceptor should be removed after minion death"
        )


# ============================================================
# Test 9: Bounce Resets Stats
# ============================================================

class TestBounceResetsStats:
    def test_bounced_minion_stats_reset_to_base(self):
        """Bounced minion has stats reset to base card_def values."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Buff the yeti with +2/+2
        game.emit(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': yeti.id, 'power_mod': 2, 'toughness_mod': 2,
                     'duration': 'permanent'},
            source='test'
        ))

        buffed_power = get_power(yeti, game.state)
        assert buffed_power == 6, f"Yeti should be buffed to 6 ATK, got {buffed_power}"

        # Bounce via RETURN_TO_HAND
        game.emit(Event(
            type=EventType.RETURN_TO_HAND,
            payload={'object_id': yeti.id},
            source='test'
        ))

        assert yeti.zone == ZoneType.HAND, (
            f"Bounced yeti should be in hand, got {yeti.zone}"
        )

        # Stats should be reset to base (4/5)
        assert yeti.characteristics.power == 4, (
            f"Bounced yeti power should reset to 4, got {yeti.characteristics.power}"
        )
        assert yeti.characteristics.toughness == 5, (
            f"Bounced yeti toughness should reset to 5, got {yeti.characteristics.toughness}"
        )


# ============================================================
# Test 10: Bounce Resets Damage
# ============================================================

class TestBounceResetsDamage:
    def test_bounced_minion_damage_cleared(self):
        """Bounced minion has damage cleared."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)

        # Deal 3 damage to yeti
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': yeti.id, 'amount': 3, 'source': 'test'},
            source='test'
        ))
        assert yeti.state.damage == 3, f"Yeti should have 3 damage, got {yeti.state.damage}"

        # Bounce
        game.emit(Event(
            type=EventType.RETURN_TO_HAND,
            payload={'object_id': yeti.id},
            source='test'
        ))

        assert yeti.state.damage == 0, (
            f"Bounced yeti damage should be 0, got {yeti.state.damage}"
        )


# ============================================================
# Test 11: Bounce Resets Summoning Sickness
# ============================================================

class TestBounceResetsSummoningSickness:
    def test_returned_minion_has_summoning_sickness(self):
        """Returned minion gets summoning sickness set to True (will have it again when replayed)."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p1)
        # Simulate clearing summoning sickness (as if a turn passed)
        yeti.state.summoning_sickness = False

        # Bounce
        game.emit(Event(
            type=EventType.RETURN_TO_HAND,
            payload={'object_id': yeti.id},
            source='test'
        ))

        # In HS, bounce resets summoning_sickness to True (obj.state.summoning_sickness = True
        # per pipeline.py line 805)
        assert yeti.state.summoning_sickness is True, (
            "Bounced minion should have summoning sickness reset to True"
        )


# ============================================================
# Test 12: Sap Returns Enemy Minion
# ============================================================

class TestSapBounce:
    def test_sap_returns_enemy_minion_to_hand(self):
        """Sap returns enemy minion to opponent's hand."""
        game, p1, p2 = new_hs_game("Rogue", "Mage")

        # Place an enemy minion for p2
        enemy_yeti = make_obj(game, CHILLWIND_YETI, p2)
        assert enemy_yeti.zone == ZoneType.BATTLEFIELD

        battlefield = game.state.zones.get('battlefield')
        assert enemy_yeti.id in battlefield.objects

        # Cast Sap (targets a random enemy minion)
        random.seed(42)
        cast_spell(game, SAP, p1)

        # Enemy minion should be in p2's hand
        hand_key = f"hand_{p2.id}"
        assert enemy_yeti.zone == ZoneType.HAND, (
            f"Sap should return enemy minion to hand, got {enemy_yeti.zone}"
        )
        assert enemy_yeti.id in game.state.zones[hand_key].objects, (
            "Enemy minion should be in opponent's hand zone list"
        )
        assert enemy_yeti.id not in battlefield.objects, (
            "Enemy minion should no longer be on battlefield"
        )


# ============================================================
# Test 13: Discard Removes from Hand
# ============================================================

class TestDiscardRemovesFromHand:
    def test_discarded_card_removed_from_hand(self):
        """Discarded card removed from hand zone and placed in graveyard."""
        game, p1, p2 = new_hs_game()

        # Create a card in hand
        card = game.create_object(
            name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
            characteristics=WISP.characteristics, card_def=WISP
        )

        hand_key = f"hand_{p1.id}"
        graveyard_key = f"graveyard_{p1.id}"

        assert card.id in game.state.zones[hand_key].objects, (
            "Card should start in hand"
        )

        # Discard the specific card
        game.emit(Event(
            type=EventType.DISCARD,
            payload={'object_id': card.id, 'player': p1.id},
            source='test'
        ))

        assert card.id not in game.state.zones[hand_key].objects, (
            "Discarded card should no longer be in hand"
        )
        assert card.zone == ZoneType.GRAVEYARD, (
            f"Discarded card zone should be GRAVEYARD, got {card.zone}"
        )
        assert card.id in game.state.zones[graveyard_key].objects, (
            "Discarded card should be in graveyard zone list"
        )


# ============================================================
# Test 14: Transform Replaces in Zone
# ============================================================

class TestTransformReplacesInZone:
    def test_polymorph_transforms_minion_on_battlefield(self):
        """Polymorph transforms minion on battlefield -- stays in same zone but with new stats."""
        game, p1, p2 = new_hs_game()

        yeti = make_obj(game, CHILLWIND_YETI, p2)
        yeti_id = yeti.id

        battlefield = game.state.zones.get('battlefield')
        assert yeti_id in battlefield.objects

        # Cast Polymorph targeting the yeti
        cast_spell(game, POLYMORPH, p1, targets=[yeti_id])

        # Yeti should still be on battlefield (same object ID, transformed)
        assert yeti_id in battlefield.objects, (
            "Transformed minion should still be on battlefield"
        )
        assert yeti.zone == ZoneType.BATTLEFIELD, (
            f"Transformed minion zone should still be BATTLEFIELD, got {yeti.zone}"
        )

        # Should now be a 1/1 Sheep
        assert yeti.name == "Sheep", (
            f"Transformed minion should be named Sheep, got {yeti.name}"
        )
        assert get_power(yeti, game.state) == 1, (
            f"Sheep should have 1 power, got {get_power(yeti, game.state)}"
        )
        assert get_toughness(yeti, game.state) == 1, (
            f"Sheep should have 1 toughness, got {get_toughness(yeti, game.state)}"
        )

        # Should not be in graveyard
        graveyard_key = f"graveyard_{p2.id}"
        assert yeti_id not in game.state.zones[graveyard_key].objects, (
            "Transformed minion should not be in graveyard"
        )


# ============================================================
# Test 15: Zone Counts Accurate
# ============================================================

class TestZoneCountsAccurate:
    def test_zone_counts_after_transitions(self):
        """After various transitions, zone object counts match expected values."""
        game, p1, p2 = new_hs_game()

        library_key = f"library_{p1.id}"
        hand_key = f"hand_{p1.id}"
        graveyard_key = f"graveyard_{p1.id}"
        battlefield = game.state.zones.get('battlefield')

        # Track initial battlefield count (heroes and hero powers may be there)
        bf_initial = len(battlefield.objects)

        # 1. Add 5 cards to library
        add_library_cards(game, p1, WISP, 5)
        assert len(game.state.zones[library_key].objects) == 5, (
            "Library should have 5 cards after adding"
        )

        # 2. Draw 2 cards: library=3, hand=2
        game.draw_cards(p1.id, 2)
        assert len(game.state.zones[library_key].objects) == 3, (
            f"Library should have 3 after drawing 2, got {len(game.state.zones[library_key].objects)}"
        )
        assert len(game.state.zones[hand_key].objects) == 2, (
            f"Hand should have 2 after drawing 2, got {len(game.state.zones[hand_key].objects)}"
        )

        # 3. Play a minion directly to battlefield
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        assert len(battlefield.objects) == bf_initial + 1, (
            f"Battlefield should have {bf_initial + 1} objects, "
            f"got {len(battlefield.objects)}"
        )

        # 4. Destroy the minion: battlefield back to initial, graveyard +1
        game.destroy(yeti.id)
        assert len(battlefield.objects) == bf_initial, (
            f"Battlefield should return to {bf_initial}, "
            f"got {len(battlefield.objects)}"
        )
        assert len(game.state.zones[graveyard_key].objects) == 1, (
            f"Graveyard should have 1 after destruction, "
            f"got {len(game.state.zones[graveyard_key].objects)}"
        )

        # 5. Discard a card from hand: hand -1, graveyard +1
        hand_objs = game.state.zones[hand_key].objects
        if hand_objs:
            card_to_discard = hand_objs[0]
            game.emit(Event(
                type=EventType.DISCARD,
                payload={'object_id': card_to_discard, 'player': p1.id},
                source='test'
            ))
            assert len(game.state.zones[hand_key].objects) == 1, (
                f"Hand should have 1 after discarding, "
                f"got {len(game.state.zones[hand_key].objects)}"
            )
            assert len(game.state.zones[graveyard_key].objects) == 2, (
                f"Graveyard should have 2 after discard, "
                f"got {len(game.state.zones[graveyard_key].objects)}"
            )

        # Final tally: library=3, hand=1, battlefield=initial, graveyard=2
        assert len(game.state.zones[library_key].objects) == 3
        assert len(game.state.zones[hand_key].objects) == 1
        assert len(battlefield.objects) == bf_initial
        assert len(game.state.zones[graveyard_key].objects) == 2


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
