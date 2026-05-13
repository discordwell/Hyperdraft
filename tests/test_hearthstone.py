"""
Hearthstone Mode Tests

Tests for Hearthstone game mode functionality.
"""

import pytest
import asyncio
from src.engine.game import Game
from src.engine.types import GameState, ZoneType, CardType, EventType, Event
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.basic import (
    WISP, STONETUSK_BOAR, CHILLWIND_YETI, BLOODFEN_RAPTOR, BOULDERFIST_OGRE,
    SEN_JIN_SHIELDMASTA,
)
from src.cards.hearthstone.warlock import SHADOWFLAME
from src.cards.hearthstone.rogue import SAP, ASSASSINATE
from src.cards.hearthstone.warrior import EXECUTE
from src.cards.hearthstone.priest import (
    SHADOW_WORD_PAIN, SHADOW_WORD_DEATH, SHADOW_MADNESS, CABAL_SHADOW_PRIEST,
)
from src.cards.hearthstone import riftclash, frierenrift


def test_game_mode_initialization():
    """Test that game initializes correctly in Hearthstone mode."""
    game = Game(mode="hearthstone")
    assert game.state.game_mode == "hearthstone"
    assert game.state.max_hand_size == 10


def test_mtg_mode_initialization():
    """Test that game still works in MTG mode."""
    game = Game(mode="mtg")
    assert game.state.game_mode == "mtg"
    assert game.state.max_hand_size == 7


def test_hearthstone_player_setup():
    """Test setting up a Hearthstone player with hero and hero power."""
    game = Game(mode="hearthstone")

    # Add player
    player = game.add_player("Player 1", life=30)

    # Set up hero
    hero_def = HEROES["Mage"]
    hero_power_def = HERO_POWERS["Mage"]
    game.setup_hearthstone_player(player, hero_def, hero_power_def)

    # Verify hero was created
    assert player.hero_id is not None
    assert player.hero_power_id is not None
    assert player.life == 30

    # Verify hero is on battlefield
    hero = game.state.objects[player.hero_id]
    assert hero.zone == ZoneType.BATTLEFIELD
    assert hero.name == "Jaina Proudmoore"

    # Verify hero power is in command zone
    hero_power = game.state.objects[player.hero_power_id]
    assert hero_power.zone == ZoneType.COMMAND
    assert hero_power.name == "Fireblast"


def test_mana_crystal_system():
    """Test Hearthstone mana crystal system."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Initial mana
    assert player.mana_crystals == 0
    assert player.mana_crystals_available == 0

    # Gain mana crystals
    game.mana_system.on_turn_start(player.id)
    assert player.mana_crystals == 1
    assert player.mana_crystals_available == 1

    # Spend mana
    game.mana_system.pay_cost(player.id, 1)
    assert player.mana_crystals == 1
    assert player.mana_crystals_available == 0

    # Gain more crystals
    for _ in range(5):
        game.mana_system.on_turn_start(player.id)

    assert player.mana_crystals == 6
    assert player.mana_crystals_available == 6

    # Test max crystals (10)
    for _ in range(10):
        game.mana_system.on_turn_start(player.id)

    assert player.mana_crystals == 10
    assert player.mana_crystals_available == 10


def test_divine_shield():
    """Test Divine Shield mechanic."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Create a minion with divine shield
    minion = game.create_object(
        name="Shielded Minion",
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD
    )
    minion.state.divine_shield = True
    minion.characteristics.power = 2
    minion.characteristics.toughness = 2

    # Deal damage - should break shield and prevent damage
    events = game.deal_damage(minion.id, minion.id, 1)

    # Shield should be broken
    assert not minion.state.divine_shield

    # Minion should still be alive (damage was prevented)
    assert minion.state.damage_marked == 0


def test_frozen_mechanic():
    """Test Freeze mechanic."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Create a minion
    minion = game.create_object(
        name="Test Minion",
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD
    )

    # Freeze it
    minion.state.frozen = True

    # Try to attack - should fail
    assert not game.combat_manager._can_attack(minion.id, player.id)

    # Unfreeze
    minion.state.frozen = False
    # Now could attack (if other conditions are met)
    # Just verify frozen check passes
    assert minion.state.frozen == False


def test_hand_size_limit():
    """Test hand size limit and overdraw."""
    game = Game(mode="hearthstone")
    player = game.add_player("Player 1")

    # Add 10 cards to hand
    hand_key = f"hand_{player.id}"
    library_key = f"library_{player.id}"

    for i in range(10):
        card = game.create_object(
            name=f"Card {i}",
            owner_id=player.id,
            zone=ZoneType.HAND
        )

    # Verify hand is full
    assert len(game.state.zones[hand_key].objects) == 10

    # Add one more card to library
    extra_card = game.create_object(
        name="Extra Card",
        owner_id=player.id,
        zone=ZoneType.LIBRARY
    )

    # Try to draw - should burn the card
    game.draw_cards(player.id, 1)

    # Hand should still be 10
    assert len(game.state.zones[hand_key].objects) == 10

    # Card should be in graveyard
    graveyard_key = f"graveyard_{player.id}"
    assert extra_card.id in game.state.zones[graveyard_key].objects


@pytest.mark.asyncio
async def test_hearthstone_turn_structure():
    """Test simplified Hearthstone turn structure."""
    game = Game(mode="hearthstone")

    # Add two players
    player1 = game.add_player("Player 1")
    player2 = game.add_player("Player 2")

    # Set up heroes
    game.setup_hearthstone_player(player1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(player2, HEROES["Warrior"], HERO_POWERS["Warrior"])

    # Set turn order
    game.turn_manager.set_turn_order([player1.id, player2.id])

    # Run first turn
    await game.turn_manager.run_turn(player1.id)

    # Check mana was gained
    assert player1.mana_crystals >= 1

    # Check hero power was reset
    assert not player1.hero_power_used


def test_hearthstone_card_creation():
    """Test that Hearthstone card factories work."""
    # Test hero creation
    hero_def = HEROES["Mage"]
    assert hero_def is not None
    assert hero_def.name == "Jaina Proudmoore"

    # Test hero power creation
    hero_power_def = HERO_POWERS["Mage"]
    assert hero_power_def is not None
    assert hero_power_def.name == "Fireblast"

    # Test minion creation
    assert WISP.name == "Wisp"
    assert WISP.characteristics.power == 1
    assert WISP.characteristics.toughness == 1

    assert STONETUSK_BOAR.name == "Stonetusk Boar"
    assert any(a.get('keyword') == 'charge' for a in STONETUSK_BOAR.abilities)

    assert CHILLWIND_YETI.name == "Chillwind Yeti"
    assert CHILLWIND_YETI.characteristics.power == 4
    assert CHILLWIND_YETI.characteristics.toughness == 5


# ============================================================
# Shadowflame — Phase 4 PendingChoice demo
# ============================================================


def _make_shadowflame_scene():
    """Set up a Hearthstone game with two friendly minions for the caster.

    No AI handler is registered, so Shadowflame's PendingChoice will stay
    pending (human path).
    """
    game = Game(mode="hearthstone")
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
    return game, p1, p2


def _make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_shadowflame_emits_pending_choice_for_human_caster():
    """Casting Shadowflame with no AI registered should leave a PendingChoice
    on state, list all friendly minions as options, and NOT auto-sacrifice."""
    game, p1, _p2 = _make_shadowflame_scene()
    yeti = _make_obj(game, CHILLWIND_YETI, p1)          # 4/5
    boar = _make_obj(game, STONETUSK_BOAR, p1)          # 1/1
    wisp = _make_obj(game, WISP, p1)                    # 1/1
    enemy = _make_obj(game, BLOODFEN_RAPTOR, _p2)       # 3/2 (untouched)

    # Cast Shadowflame.
    shadowflame_obj = game.create_object(
        name=SHADOWFLAME.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SHADOWFLAME.characteristics,
        card_def=SHADOWFLAME,
    )
    events = SHADOWFLAME.spell_effect(shadowflame_obj, game.state, [])

    # Human path: no events emitted yet, choice is pending.
    assert events == [], f"Expected no immediate events on human path, got {events}"

    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    assert pc.player == p1.id
    assert pc.source_id == shadowflame_obj.id

    option_ids = {opt["id"] for opt in pc.options}
    assert yeti.id in option_ids
    assert boar.id in option_ids
    assert wisp.id in option_ids
    assert enemy.id not in option_ids  # enemy minions aren't options

    # No sacrifice has happened yet — the yeti is still alive.
    assert yeti.state.damage == 0
    destroy_events = [
        e for e in game.state.event_log
        if e.type == EventType.OBJECT_DESTROYED
        and e.payload.get("reason") == "shadowflame"
    ]
    assert destroy_events == []


def test_shadowflame_heuristic_pick_preserves_ai_max_attack_target():
    """The pending choice's heuristic_pick must equal the highest-attack
    friendly minion id — the prior AI behavior. This preserves the
    auto-pick when the caster is an AI player.
    """
    game, p1, _p2 = _make_shadowflame_scene()
    yeti = _make_obj(game, CHILLWIND_YETI, p1)      # 4/5 — biggest power
    boar = _make_obj(game, STONETUSK_BOAR, p1)      # 1/1
    wisp = _make_obj(game, WISP, p1)                # 1/1

    shadowflame_obj = game.create_object(
        name=SHADOWFLAME.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SHADOWFLAME.characteristics,
        card_def=SHADOWFLAME,
    )
    SHADOWFLAME.spell_effect(shadowflame_obj, game.state, [])

    pc = game.state.pending_choice
    assert pc is not None
    hp = (pc.callback_data or {}).get("heuristic_pick")
    assert hp == [yeti.id], (
        f"heuristic_pick should be the max-attack friendly minion "
        f"(Yeti @ {yeti.characteristics.power} ATK), got {hp}"
    )


def test_shadowflame_no_friendly_minions_short_circuits():
    """With no friendly minions on board, Shadowflame is a no-op:
    returns [] and does NOT stash a PendingChoice (would be unsatisfiable)."""
    game, p1, _p2 = _make_shadowflame_scene()
    # p2 has a minion, but that doesn't count for the caster (p1).
    _make_obj(game, BLOODFEN_RAPTOR, _p2)

    shadowflame_obj = game.create_object(
        name=SHADOWFLAME.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SHADOWFLAME.characteristics,
        card_def=SHADOWFLAME,
    )
    events = SHADOWFLAME.spell_effect(shadowflame_obj, game.state, [])

    assert events == []
    assert game.state.pending_choice is None


# ============================================================
# PendingChoice migrations — deterministic-pick cards (Phase 5)
# ============================================================
#
# Each card here used to auto-pick via random.choice over a deterministic
# bucket. The new path emits a PendingChoice over the bucket so humans
# can deviate from the heuristic. AI behavior is preserved by registering
# the caster as AI; the helper resolves inline via heuristic_pick.


def _hs_scene(p1_class="Mage", p2_class="Warrior"):
    """Build a Hearthstone game with both heroes set up."""
    game = Game(mode="hearthstone")
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
    return game, p1, p2


def _cast(game, card_def, owner, targets=None):
    """Cast helper that returns (caster_obj, returned_events). Emits events
    so AI-path callers can assert against the engine's event_log.
    """
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    events = card_def.spell_effect(obj, game.state, targets) if card_def.spell_effect else []
    for e in events:
        game.emit(e)
    return obj, events


# ---- Sap (rogue): bounce an enemy minion ----

def test_sap_emits_pending_choice_for_human_caster():
    """Sap on a human caster leaves a PendingChoice over enemy minions."""
    game, p1, p2 = _hs_scene()
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    yeti = _make_obj(game, CHILLWIND_YETI, p2)
    boar = _make_obj(game, STONETUSK_BOAR, p2)

    sap_obj, events = _cast(game, SAP, p1)

    # Human path: choice stashed, no bounce yet.
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    assert pc.player == p1.id
    option_ids = {opt["id"] for opt in pc.options}
    assert ogre.id in option_ids
    assert yeti.id in option_ids
    assert boar.id in option_ids

    # Heuristic should target the 6-attack Ogre.
    hp = (pc.callback_data or {}).get("heuristic_pick")
    assert hp == [ogre.id]

    # No RETURN_TO_HAND event yet.
    bounce = [e for e in game.state.event_log if e.type == EventType.RETURN_TO_HAND]
    assert bounce == []


def test_sap_heuristic_resolves_for_ai_caster():
    """When the caster is AI, Sap resolves inline against the heuristic pick."""
    game, p1, p2 = _hs_scene()
    game.turn_manager.ai_players.add(p1.id)
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    _make_obj(game, WISP, p2)

    _sap, _events = _cast(game, SAP, p1)

    assert game.state.pending_choice is None
    bounce = [e for e in game.state.event_log
              if e.type == EventType.RETURN_TO_HAND
              and e.payload.get("object_id") == ogre.id]
    assert len(bounce) == 1


def test_sap_no_enemy_minions_short_circuits():
    """No enemies = no choice, no events."""
    game, p1, _p2 = _hs_scene()
    _sap, events = _cast(game, SAP, p1)
    assert events == []
    assert game.state.pending_choice is None


def test_sap_legacy_explicit_target_bypasses_choice():
    """A test that passes targets=[explicit] uses the legacy path."""
    game, p1, p2 = _hs_scene()
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    wisp = _make_obj(game, WISP, p2)

    # Explicitly pick the Wisp; legacy path should bounce it without a choice.
    _sap, events = _cast(game, SAP, p1, targets=[wisp.id])
    assert game.state.pending_choice is None
    assert any(
        e.type == EventType.RETURN_TO_HAND and e.payload.get("object_id") == wisp.id
        for e in events
    ), f"Expected wisp to be returned to hand, got {events}"


# ---- Assassinate (rogue): destroy an enemy minion ----

def test_assassinate_emits_pending_choice_for_human():
    game, p1, p2 = _hs_scene()
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    yeti = _make_obj(game, CHILLWIND_YETI, p2)

    _ass, events = _cast(game, ASSASSINATE, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert pc.choice_type == "target"
    assert {opt["id"] for opt in pc.options} == {ogre.id, yeti.id}
    assert (pc.callback_data or {}).get("heuristic_pick") == [ogre.id]


def test_assassinate_heuristic_kills_for_ai():
    game, p1, p2 = _hs_scene()
    game.turn_manager.ai_players.add(p1.id)
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)

    _ass, _events = _cast(game, ASSASSINATE, p1)
    destroyed = [e for e in game.state.event_log
                 if e.type == EventType.OBJECT_DESTROYED
                 and e.payload.get("reason") == "assassinate"
                 and e.payload.get("object_id") == ogre.id]
    assert len(destroyed) == 1


def test_assassinate_no_enemies_short_circuits():
    game, p1, _p2 = _hs_scene()
    _ass, events = _cast(game, ASSASSINATE, p1)
    assert events == []
    assert game.state.pending_choice is None


# ---- Execute (warrior): destroy a damaged enemy minion ----

def test_execute_emits_pending_choice_for_human_over_damaged_only():
    game, p1, p2 = _hs_scene()
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)  # damaged
    yeti = _make_obj(game, CHILLWIND_YETI, p2)    # undamaged
    ogre.state.damage = 1

    _exec, events = _cast(game, EXECUTE, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    # Only the damaged ogre is a legal option.
    assert {opt["id"] for opt in pc.options} == {ogre.id}
    assert (pc.callback_data or {}).get("heuristic_pick") == [ogre.id]


def test_execute_no_damaged_targets_short_circuits():
    game, p1, p2 = _hs_scene()
    _make_obj(game, CHILLWIND_YETI, p2)  # undamaged

    _exec, events = _cast(game, EXECUTE, p1)
    assert events == []
    assert game.state.pending_choice is None


def test_execute_legacy_explicit_target_path():
    game, p1, p2 = _hs_scene()
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    ogre.state.damage = 1

    _exec, events = _cast(game, EXECUTE, p1, targets=[ogre.id])
    assert game.state.pending_choice is None
    assert any(
        e.type == EventType.OBJECT_DESTROYED and e.payload.get("object_id") == ogre.id
        for e in events
    )


# ---- Shadow Word: Pain (priest): destroy ATK<=3 ----

def test_shadow_word_pain_choice_filtered_to_low_attack():
    game, p1, p2 = _hs_scene()
    senjin = _make_obj(game, SEN_JIN_SHIELDMASTA, p2)  # 3/5 — legal
    boar = _make_obj(game, STONETUSK_BOAR, p2)         # 1/1 — legal
    yeti = _make_obj(game, CHILLWIND_YETI, p2)         # 4/5 — illegal

    _swp, events = _cast(game, SHADOW_WORD_PAIN, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    opts = {opt["id"] for opt in pc.options}
    assert senjin.id in opts
    assert boar.id in opts
    assert yeti.id not in opts
    # Heuristic should be the 3-attack Sen'jin.
    assert (pc.callback_data or {}).get("heuristic_pick") == [senjin.id]


def test_shadow_word_pain_no_valid_targets():
    game, p1, p2 = _hs_scene()
    _make_obj(game, CHILLWIND_YETI, p2)  # 4/5 — too high

    _swp, events = _cast(game, SHADOW_WORD_PAIN, p1)
    assert events == []
    assert game.state.pending_choice is None


# ---- Shadow Word: Death (priest): destroy ATK>=5 ----

def test_shadow_word_death_choice_filtered_to_high_attack():
    game, p1, p2 = _hs_scene()
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7 — legal
    yeti = _make_obj(game, CHILLWIND_YETI, p2)    # 4/5 — illegal

    _swd, events = _cast(game, SHADOW_WORD_DEATH, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert {opt["id"] for opt in pc.options} == {ogre.id}
    assert (pc.callback_data or {}).get("heuristic_pick") == [ogre.id]


def test_shadow_word_death_no_valid_targets():
    game, p1, p2 = _hs_scene()
    _make_obj(game, CHILLWIND_YETI, p2)  # 4/5 — too low

    _swd, events = _cast(game, SHADOW_WORD_DEATH, p1)
    assert events == []
    assert game.state.pending_choice is None


# ---- Shadow Madness (priest): steal ATK<=3 until end of turn ----

def test_shadow_madness_choice_filtered_to_low_attack():
    game, p1, p2 = _hs_scene()
    senjin = _make_obj(game, SEN_JIN_SHIELDMASTA, p2)
    yeti = _make_obj(game, CHILLWIND_YETI, p2)

    _sm, events = _cast(game, SHADOW_MADNESS, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert senjin.id in {opt["id"] for opt in pc.options}
    assert yeti.id not in {opt["id"] for opt in pc.options}


def test_shadow_madness_heuristic_resolves_for_ai():
    game, p1, p2 = _hs_scene()
    game.turn_manager.ai_players.add(p1.id)
    senjin = _make_obj(game, SEN_JIN_SHIELDMASTA, p2)

    _sm, _events = _cast(game, SHADOW_MADNESS, p1)
    gain = [e for e in game.state.event_log
            if e.type == EventType.GAIN_CONTROL
            and e.payload.get("object_id") == senjin.id]
    assert len(gain) == 1


# ---- Cabal Shadow Priest (priest): steal ATK<=2 permanently via battlecry ----

def test_cabal_shadow_priest_battlecry_emits_choice():
    game, p1, p2 = _hs_scene()
    boar = _make_obj(game, STONETUSK_BOAR, p2)   # 1/1 — legal
    yeti = _make_obj(game, CHILLWIND_YETI, p2)   # 4/5 — illegal

    cabal_obj = _make_obj(game, CABAL_SHADOW_PRIEST, p1)
    events = CABAL_SHADOW_PRIEST.battlecry(cabal_obj, game.state)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert boar.id in {opt["id"] for opt in pc.options}
    assert yeti.id not in {opt["id"] for opt in pc.options}


def test_cabal_shadow_priest_battlecry_no_valid_targets():
    game, p1, p2 = _hs_scene()
    _make_obj(game, CHILLWIND_YETI, p2)

    cabal_obj = _make_obj(game, CABAL_SHADOW_PRIEST, p1)
    events = CABAL_SHADOW_PRIEST.battlecry(cabal_obj, game.state)
    assert events == []
    assert game.state.pending_choice is None


# ---- Cinder Lance (riftclash): branched single-target burn ----

def test_cinder_lance_emits_pending_choice_for_human():
    game = Game(mode="hearthstone")
    p1 = game.add_player("Pyro", life=30)
    p2 = game.add_player("Cryo", life=30)
    game.setup_hearthstone_player(p1, riftclash.IGNIS_REFORGED, riftclash.EMBER_VOLLEY)
    game.setup_hearthstone_player(p2, riftclash.GLACIEL_REFORGED, riftclash.CRYO_WARD)
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    wisp = _make_obj(game, WISP, p2)

    lance_obj, events = _cast(game, riftclash.CINDER_LANCE, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert {opt["id"] for opt in pc.options} == {ogre.id, wisp.id}
    assert (pc.callback_data or {}).get("heuristic_pick") == [ogre.id]


def test_cinder_lance_no_enemy_minions_falls_through_to_hero():
    """When no minions exist, Cinder Lance burns the hero directly (no choice)."""
    game = Game(mode="hearthstone")
    p1 = game.add_player("Pyro", life=30)
    p2 = game.add_player("Cryo", life=30)
    game.setup_hearthstone_player(p1, riftclash.IGNIS_REFORGED, riftclash.EMBER_VOLLEY)
    game.setup_hearthstone_player(p2, riftclash.GLACIEL_REFORGED, riftclash.CRYO_WARD)

    _lance, events = _cast(game, riftclash.CINDER_LANCE, p1)
    assert game.state.pending_choice is None
    # Hero takes 3 + a Cinder Charge added to hand.
    assert any(
        e.type == EventType.DAMAGE
        and e.payload.get("target") == p2.hero_id
        and e.payload.get("amount") == 3
        for e in events
    )


# ---- Zoltraak Bolt (frierenrift): 3 damage with choice ----

def test_zoltraak_bolt_emits_pending_choice_for_human():
    game = Game(mode="hearthstone")
    p1 = game.add_player("Frieren", life=30)
    p2 = game.add_player("Macht", life=30)
    game.setup_hearthstone_player(p1, frierenrift.FRIEREN_HERO, frierenrift.ANALYZE_FORMULA)
    game.setup_hearthstone_player(p2, frierenrift.MACHT_HERO, frierenrift.GOLD_HEX)
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    wisp = _make_obj(game, WISP, p2)

    _bolt, events = _cast(game, frierenrift.ZOLTRAAK_BOLT, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert {opt["id"] for opt in pc.options} == {ogre.id, wisp.id}
    assert (pc.callback_data or {}).get("heuristic_pick") == [ogre.id]


def test_zoltraak_bolt_no_minions_burns_hero():
    game = Game(mode="hearthstone")
    p1 = game.add_player("Frieren", life=30)
    p2 = game.add_player("Macht", life=30)
    game.setup_hearthstone_player(p1, frierenrift.FRIEREN_HERO, frierenrift.ANALYZE_FORMULA)
    game.setup_hearthstone_player(p2, frierenrift.MACHT_HERO, frierenrift.GOLD_HEX)

    _bolt, events = _cast(game, frierenrift.ZOLTRAAK_BOLT, p1)
    assert game.state.pending_choice is None
    assert any(
        e.type == EventType.DAMAGE
        and e.payload.get("target") == p2.hero_id
        and e.payload.get("amount") == 3
        for e in events
    )


# ---- Ice Shackle (riftclash): damage + freeze with choice ----

def test_ice_shackle_emits_pending_choice_for_human():
    game = Game(mode="hearthstone")
    p1 = game.add_player("Pyro", life=30)
    p2 = game.add_player("Cryo", life=30)
    game.setup_hearthstone_player(p1, riftclash.IGNIS_REFORGED, riftclash.EMBER_VOLLEY)
    game.setup_hearthstone_player(p2, riftclash.GLACIEL_REFORGED, riftclash.CRYO_WARD)
    ogre = _make_obj(game, BOULDERFIST_OGRE, p2)
    wisp = _make_obj(game, WISP, p2)

    _shackle, events = _cast(game, riftclash.ICE_SHACKLE, p1)
    assert events == []
    pc = game.state.pending_choice
    assert pc is not None
    assert {opt["id"] for opt in pc.options} == {ogre.id, wisp.id}
    assert (pc.callback_data or {}).get("heuristic_pick") == [ogre.id]


def test_ice_shackle_no_enemy_minions_short_circuits():
    game = Game(mode="hearthstone")
    p1 = game.add_player("Pyro", life=30)
    p2 = game.add_player("Cryo", life=30)
    game.setup_hearthstone_player(p1, riftclash.IGNIS_REFORGED, riftclash.EMBER_VOLLEY)
    game.setup_hearthstone_player(p2, riftclash.GLACIEL_REFORGED, riftclash.CRYO_WARD)

    _shackle, events = _cast(game, riftclash.ICE_SHACKLE, p1)
    assert events == []
    assert game.state.pending_choice is None


if __name__ == "__main__":
    # Run tests
    print("Running Hearthstone tests...")

    print("\n1. Testing game mode initialization...")
    test_game_mode_initialization()
    print("   ✓ Hearthstone mode initialized correctly")

    print("\n2. Testing MTG mode still works...")
    test_mtg_mode_initialization()
    print("   ✓ MTG mode still works")

    print("\n3. Testing Hearthstone player setup...")
    test_hearthstone_player_setup()
    print("   ✓ Hero and hero power setup correctly")

    print("\n4. Testing mana crystal system...")
    test_mana_crystal_system()
    print("   ✓ Mana crystals work correctly")

    print("\n5. Testing Divine Shield...")
    test_divine_shield()
    print("   ✓ Divine Shield prevents first damage")

    print("\n6. Testing Frozen mechanic...")
    test_frozen_mechanic()
    print("   ✓ Frozen prevents attacking")

    print("\n7. Testing hand size limit...")
    test_hand_size_limit()
    print("   ✓ Hand size limit enforced, overdraw burns cards")

    print("\n8. Testing Hearthstone card factories...")
    test_hearthstone_card_creation()
    print("   ✓ Cards created correctly")

    print("\n9. Testing turn structure...")
    asyncio.run(test_hearthstone_turn_structure())
    print("   ✓ Hearthstone turn structure works")

    print("\n10. Testing Shadowflame PendingChoice (Phase 4 demo)...")
    test_shadowflame_emits_pending_choice_for_human_caster()
    test_shadowflame_heuristic_pick_preserves_ai_max_attack_target()
    test_shadowflame_no_friendly_minions_short_circuits()
    print("   ✓ Shadowflame emits PendingChoice; heuristic_pick preserves AI behavior; empty short-circuits")

    print("\n✅ All Hearthstone tests passed!")
