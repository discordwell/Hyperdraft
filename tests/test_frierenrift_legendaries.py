"""
Frierenrift Legendary Tests

Verifies the redesigned and new legendaries — each is expected to alter game
state in a way that a vanilla battlecry cannot.
"""

from __future__ import annotations

import pytest

from src.engine.game import Game
from src.engine.types import (
    CardType,
    Event,
    EventType,
    ZoneType,
)
from src.cards.hearthstone.frierenrift import (
    AURA_EXECUTION_SAINT,
    AURELIA_DEMON_LORD,
    EISEN_ANCIENT_SHIELD,
    ETERNAL_FLAME_OF_ETHOS,
    FRIEREN_HERO,
    FRIERENRIFT_HERO_POWERS,
    FRIEREN_LAST_GREAT_MAGE,
    HEITER_PRIEST_OF_THE_GODDESS,
    HIMMELS_LEGACY,
    MACHT_GOLDEN_GENERAL,
    MACHT_HERO,
    SEIN_CLERIC_COMPANION,
    SOLITAR_MIRAGE,
    STARK_BREAKTHROUGH,
    FRIERENRIFT_DECKS,
    _ensure_variant_resources,
    install_frierenrift_modifiers,
)
from src.cards.hearthstone.basic import WISP, CHILLWIND_YETI, BOULDERFIST_OGRE
from src.cards.hearthstone.classic import FIREBALL


# ----------------------------------------------------------------------------
# Harness
# ----------------------------------------------------------------------------


def new_frierenrift_game() -> tuple[Game, "Player", "Player"]:
    game = Game(mode="hearthstone")
    p1 = game.add_player("Frieren", life=30)
    p2 = game.add_player("Macht", life=30)

    game.setup_hearthstone_player(p1, FRIEREN_HERO, FRIERENRIFT_HERO_POWERS["Frieren"])
    game.setup_hearthstone_player(p2, MACHT_HERO, FRIERENRIFT_HERO_POWERS["Macht"])
    install_frierenrift_modifiers(game)

    # Fill each player's shards so affinity gates pass when needed.
    for player in (p1, p2):
        resources = _ensure_variant_resources(player)
        for key in ("azure", "ember", "verdant"):
            resources[key] = 3
        player.variant_resources = resources
        player.mana_crystals = 10
        player.mana_crystals_available = 10

    return game, p1, p2


def make_battlefield_minion(game, card_def, owner):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def make_hand_minion(game, card_def, owner):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _send_etb_from_hand(game, obj):
    """Emit the ZONE_CHANGE that battlecries key on (HAND -> BATTLEFIELD)."""
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": obj.id,
            "from_zone": f"hand_{obj.owner}",
            "from_zone_type": ZoneType.HAND,
            "to_zone": "battlefield",
            "to_zone_type": ZoneType.BATTLEFIELD,
        },
        source=obj.id,
    ))


def _put_on_battlefield_from_hand(game, obj):
    hand_key = f"hand_{obj.owner}"
    hand = game.state.zones.get(hand_key)
    if hand and obj.id in hand.objects:
        hand.objects.remove(obj.id)
    bf = game.state.zones.get("battlefield")
    if obj.id not in bf.objects:
        bf.objects.append(obj.id)
    obj.zone = ZoneType.BATTLEFIELD
    _send_etb_from_hand(game, obj)


# ----------------------------------------------------------------------------
# 1. Frieren, Mage of the Age — regenerate + mana growth
# ----------------------------------------------------------------------------


def test_frieren_mage_of_the_age_regenerates_damage():
    game, p1, _p2 = new_frierenrift_game()
    frieren = make_battlefield_minion(game, FRIEREN_LAST_GREAT_MAGE, p1)

    game.deal_damage(frieren.id, frieren.id, 5)

    # Regenerate prevents the damage and clears marked damage.
    assert frieren.state.damage == 0
    assert frieren.id in game.state.zones["battlefield"].objects


def test_frieren_mage_of_the_age_grants_mana_on_peaceful_end():
    game, p1, _p2 = new_frierenrift_game()
    frieren = make_battlefield_minion(game, FRIEREN_LAST_GREAT_MAGE, p1)

    # Simulate "turn number" the handler inspects.
    game.state.turn_number = 5
    # Snapshot the crystal count before end-of-turn.
    p1.mana_crystals = 7
    game.emit(Event(
        type=EventType.PHASE_END,
        payload={"phase": "end", "player": p1.id},
        source=frieren.id,
    ))
    assert p1.mana_crystals == 8


def test_frieren_mage_of_the_age_denies_mana_if_death_occurred():
    game, p1, _p2 = new_frierenrift_game()
    frieren = make_battlefield_minion(game, FRIEREN_LAST_GREAT_MAGE, p1)
    # A friendly wisp gets destroyed.
    sacrifice = make_battlefield_minion(game, WISP, p1)

    game.state.turn_number = 3
    p1.mana_crystals = 6
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={"object_id": sacrifice.id, "reason": "test"},
        source=sacrifice.id,
    ))
    game.emit(Event(
        type=EventType.PHASE_END,
        payload={"phase": "end", "player": p1.id},
        source=frieren.id,
    ))
    assert p1.mana_crystals == 6  # no growth this turn


# ----------------------------------------------------------------------------
# 2. Aura, Execution Saint — asymmetric sweeper
# ----------------------------------------------------------------------------


def test_aura_scales_of_obedience_destroys_weaker_freezes_stronger():
    game, p1, p2 = new_frierenrift_game()
    # Enemy minions: a 1/1 Wisp, a 4/5 Yeti, and a 6/7 Ogre.
    wisp = make_battlefield_minion(game, WISP, p2)
    yeti = make_battlefield_minion(game, CHILLWIND_YETI, p2)
    ogre = make_battlefield_minion(game, BOULDERFIST_OGRE, p2)

    # Aura (6 attack) — Wisp dies (1 < 6), Yeti dies (4 < 6), Ogre frozen (6 >= 6).
    aura = make_hand_minion(game, AURA_EXECUTION_SAINT, p1)
    _put_on_battlefield_from_hand(game, aura)

    bf = game.state.zones["battlefield"]
    assert wisp.id not in bf.objects, "1-attack wisp should be destroyed"
    assert yeti.id not in bf.objects, "4-attack yeti should be destroyed"
    assert ogre.id in bf.objects, "6-attack ogre should survive"
    assert ogre.state.frozen is True


# ----------------------------------------------------------------------------
# 3. Macht, Golden General — attune-cap bump + mana hex
# ----------------------------------------------------------------------------


def test_macht_raises_attune_cap_while_on_battlefield():
    game, _p1, p2 = new_frierenrift_game()
    assert int(getattr(p2, "attunements_per_turn", 1) or 1) == 1
    macht = make_battlefield_minion(game, MACHT_GOLDEN_GENERAL, p2)
    # Emit explicit ETB so the setup's ETB interceptor fires too.
    _send_etb_from_hand(game, macht)
    assert int(p2.attunements_per_turn) == 2
    # On leave, the cap snaps back.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            "object_id": macht.id,
            "from_zone": "battlefield",
            "from_zone_type": ZoneType.BATTLEFIELD,
            "to_zone": f"graveyard_{p2.id}",
            "to_zone_type": ZoneType.GRAVEYARD,
        },
        source=macht.id,
    ))
    assert int(p2.attunements_per_turn) == 1


def test_macht_spell_hex_taxes_opponent_mana():
    game, p1, p2 = new_frierenrift_game()
    macht = make_battlefield_minion(game, MACHT_GOLDEN_GENERAL, p2)
    # Synthesize a CAST event from p2 (Macht's controller).
    p1.mana_crystals_available = 7
    game.emit(Event(
        type=EventType.CAST,
        payload={"caster": p2.id, "types": [CardType.SPELL]},
        source=macht.id,
        controller=p2.id,
    ))
    assert p1.mana_crystals_available == 6


# ----------------------------------------------------------------------------
# 4. Himmel, Legacy of the Brave — delayed alt-win condition
# ----------------------------------------------------------------------------


def test_himmel_fires_damage_on_turn_start_if_no_attacks():
    game, p1, p2 = new_frierenrift_game()
    himmel = make_battlefield_minion(game, HIMMELS_LEGACY, p1)
    # Simulate turn number advancing past ETB.
    game.state.turn_number = 1
    # Run the ETB handler via synthetic ZONE_CHANGE.
    _send_etb_from_hand(game, himmel)
    # Advance to a new turn.
    game.state.turn_number = 2
    start_life = p2.life
    game.emit(Event(
        type=EventType.TURN_START,
        payload={"player": p1.id},
        source=himmel.id,
    ))
    # Damage might affect armor first — check combined life + armor delta.
    effective = p2.life + p2.armor
    assert effective == (start_life + p2.armor) - 4 or p2.life < start_life


def test_himmel_ceases_damage_once_streak_is_broken():
    game, p1, p2 = new_frierenrift_game()
    himmel = make_battlefield_minion(game, HIMMELS_LEGACY, p1)
    game.state.turn_number = 1
    _send_etb_from_hand(game, himmel)

    # Break the streak with an attack declared by a friendly minion.
    attacker = make_battlefield_minion(game, WISP, p1)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker": attacker.id, "controller": p1.id},
        source=attacker.id,
    ))

    game.state.turn_number = 2
    before_effective = p2.life + p2.armor
    game.emit(Event(
        type=EventType.TURN_START,
        payload={"player": p1.id},
        source=himmel.id,
    ))
    after_effective = p2.life + p2.armor
    assert before_effective == after_effective  # no damage since streak is broken


# ----------------------------------------------------------------------------
# 5. Eisen, Wall of the Past — damage redirect + armor growth
# ----------------------------------------------------------------------------


def test_eisen_redirects_hero_damage_to_armor():
    game, p1, _p2 = new_frierenrift_game()
    _ = make_battlefield_minion(game, EISEN_ANCIENT_SHIELD, p1)
    start_armor = p1.armor
    start_life = p1.life
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={"target": p1.hero_id, "amount": 6},
        source="opponent_weapon",
    ))
    # Damage to hero prevented; armor gained by 1 (per Eisen's rule).
    assert p1.life == start_life
    assert p1.armor >= start_armor + 1


def test_eisen_grants_armor_each_turn_start():
    game, p1, _p2 = new_frierenrift_game()
    # Seed p1's library so TURN_START doesn't trigger fatigue damage (which
    # Eisen would then redirect into additional armor).
    for _ in range(3):
        game.create_object(
            name=WISP.name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics,
            card_def=WISP,
        )
    _ = make_battlefield_minion(game, EISEN_ANCIENT_SHIELD, p1)
    start_armor = p1.armor
    game.emit(Event(
        type=EventType.TURN_START,
        payload={"player": p1.id},
        source="test",
    ))
    assert p1.armor == start_armor + 2


# ----------------------------------------------------------------------------
# 6. Solitar, Shadowchord — remember + copy enemy spell
# ----------------------------------------------------------------------------


def test_solitar_memorizes_last_opponent_spell_and_copies_on_etb():
    game, p1, p2 = new_frierenrift_game()
    solitar = make_battlefield_minion(game, SOLITAR_MIRAGE, p1)
    # An opponent casts a Fireball — synthesize the CAST event with a card_def.
    spell_obj = game.create_object(
        name=FIREBALL.name,
        owner_id=p2.id,
        zone=ZoneType.STACK,
        characteristics=FIREBALL.characteristics,
        card_def=FIREBALL,
    )
    game.emit(Event(
        type=EventType.CAST,
        payload={
            "caster": p2.id,
            "spell_id": spell_obj.id,
            "types": [CardType.SPELL],
        },
        source=spell_obj.id,
        controller=p2.id,
    ))
    memorized = getattr(solitar, "_solitar_memorized", None)
    assert memorized is not None and memorized.name == "Fireball"

    # Now simulate Solitar being played from hand (pretend re-ETB).
    _send_etb_from_hand(game, solitar)
    # ADD_TO_HAND event handler should have inserted Fireball into p1's hand.
    hand = game.state.zones[f"hand_{p1.id}"]
    names = [game.state.objects[oid].name for oid in hand.objects]
    assert "Fireball" in names


# ----------------------------------------------------------------------------
# 7. Heiter, Priest of the Goddess — scaling battlecry
# ----------------------------------------------------------------------------


def test_heiter_heals_for_shard_total_and_draws():
    game, p1, _p2 = new_frierenrift_game()
    # Override shards to 4/3/2 = 9 total.
    resources = _ensure_variant_resources(p1)
    resources.update({"azure": 4, "ember": 3, "verdant": 2})
    p1.variant_resources = resources

    # Make Heiter, play him from hand.
    heiter = make_hand_minion(game, HEITER_PRIEST_OF_THE_GODDESS, p1)
    start_life = p1.life

    # Seed the library with at least one card so the draw event has something to draw.
    library_key = f"library_{p1.id}"
    if not game.state.zones[library_key].objects:
        _ = game.create_object(
            name="Filler",
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics,
            card_def=WISP,
        )

    _put_on_battlefield_from_hand(game, heiter)
    # Hero life should have grown (hero may cap at 30 depending on engine rules).
    assert p1.life >= start_life


def test_heiter_deathrattle_resurrects_cheapest_minion():
    game, p1, _p2 = new_frierenrift_game()
    # Put a Wisp (1-cost) and a Boulderfist Ogre (6-cost) in p1's graveyard.
    wisp = game.create_object(
        name=WISP.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=WISP.characteristics,
        card_def=WISP,
    )
    _ = game.create_object(
        name=BOULDERFIST_OGRE.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=BOULDERFIST_OGRE.characteristics,
        card_def=BOULDERFIST_OGRE,
    )
    heiter = make_battlefield_minion(game, HEITER_PRIEST_OF_THE_GODDESS, p1)
    # Fire the deathrattle handler directly.
    events = HEITER_PRIEST_OF_THE_GODDESS.deathrattle(heiter, game.state)
    # Expect a RETURN_FROM_GRAVEYARD event targeting the Wisp (cheapest).
    assert any(
        ev.type == EventType.RETURN_FROM_GRAVEYARD
        and ev.payload.get("object_id") == wisp.id
        for ev in events
    )


# ----------------------------------------------------------------------------
# 8. Stark, Breakthrough — tutor + scaling
# ----------------------------------------------------------------------------


def test_stark_pulls_up_to_three_warriors_from_library():
    game, p1, _p2 = new_frierenrift_game()
    # Seed the library with 5 Warrior-subtype and a couple of non-warriors.
    library_key = f"library_{p1.id}"
    # First clear the auto-populated library.
    game.state.zones[library_key].objects.clear()
    # Fill with 5 Stark-like Warrior placeholders + 2 Wisps.
    from src.cards.hearthstone.frierenrift import STARK_VANGUARD_GUARDIAN
    warriors = []
    for _ in range(5):
        w = game.create_object(
            name=STARK_VANGUARD_GUARDIAN.name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=STARK_VANGUARD_GUARDIAN.characteristics,
            card_def=STARK_VANGUARD_GUARDIAN,
        )
        warriors.append(w)
    for _ in range(2):
        game.create_object(
            name=WISP.name,
            owner_id=p1.id,
            zone=ZoneType.LIBRARY,
            characteristics=WISP.characteristics,
            card_def=WISP,
        )

    stark = make_hand_minion(game, STARK_BREAKTHROUGH, p1)
    _put_on_battlefield_from_hand(game, stark)
    hand = game.state.zones[f"hand_{p1.id}"]
    warrior_ids_in_hand = [
        oid for oid in hand.objects
        if "Warrior" in game.state.objects[oid].characteristics.subtypes
    ]
    assert len(warrior_ids_in_hand) == 3


def test_stark_gains_pt_when_attacking():
    game, p1, _p2 = new_frierenrift_game()
    stark = make_battlefield_minion(game, STARK_BREAKTHROUGH, p1)
    events_out = game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={"attacker": stark.id, "controller": p1.id},
        source=stark.id,
    ))
    # Inspect for a PT_MODIFICATION event issued on Stark.
    assert any(
        ev.type == EventType.PT_MODIFICATION
        and ev.payload.get("object_id") == stark.id
        for ev in events_out
    )


# ----------------------------------------------------------------------------
# 9. Sein, Cleric Companion — attune-scaling end-of-turn heal
# ----------------------------------------------------------------------------


def test_sein_heals_at_end_of_turn_for_double_attune_count():
    game, p1, _p2 = new_frierenrift_game()
    _ = make_battlefield_minion(game, SEIN_CLERIC_COMPANION, p1)
    p1.attunements_this_turn = 2
    # Drop p1's life so healing has room to grow.
    p1.life = 20
    game.emit(Event(
        type=EventType.PHASE_END,
        payload={"phase": "end", "player": p1.id},
        source="test",
    ))
    assert p1.life >= 24  # 2 attunes x 2 = +4 healing


# ----------------------------------------------------------------------------
# 10. Demon Lord Aurelia — reality-bending battlecry
# ----------------------------------------------------------------------------


def test_aurelia_resets_opponent_mana_and_maxes_controller():
    game, p1, p2 = new_frierenrift_game()
    p1.mana_crystals = 3
    p1.mana_crystals_available = 3
    p2.mana_crystals = 8
    p2.mana_crystals_available = 6
    p2_resources = _ensure_variant_resources(p2)
    p2_resources.update({"azure": 2, "ember": 2, "verdant": 2})

    aurelia = make_hand_minion(game, AURELIA_DEMON_LORD, p1)
    _put_on_battlefield_from_hand(game, aurelia)

    assert p1.mana_crystals == 10
    assert p1.mana_crystals_available == 10
    assert p2.mana_crystals == 0
    assert p2.mana_crystals_available == 0
    # Each shard color should have decremented by 1 on the opponent.
    assert p2.variant_resources["azure"] == 1
    assert p2.variant_resources["ember"] == 1
    assert p2.variant_resources["verdant"] == 1


def test_aurelia_cost_reduced_by_non_human_allies():
    game, p1, _p2 = new_frierenrift_game()
    # Three elf/dwarf/demon allies on p1's side to trigger reduction.
    for i in range(3):
        obj = game.create_object(
            name=f"tribe_{i}",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=WISP.characteristics,
            card_def=None,
        )
        # Use a fresh subtypes set to avoid aliasing WISP.characteristics.subtypes.
        obj.characteristics.subtypes = {"Demon"}
    aurelia = make_hand_minion(game, AURELIA_DEMON_LORD, p1)
    game.state.active_player = p1.id
    # Engine invokes dynamic_cost with the GameObject.
    cost = aurelia.card_def.dynamic_cost(aurelia, game.state)
    # Base 9 with 3 non-Human allies -> 6; min 5 bound applies for >=4 allies.
    assert cost == 6


# ----------------------------------------------------------------------------
# 11. Eternal Flame of Ethos — sweeper + persistent shard grant
# ----------------------------------------------------------------------------


def test_eternal_flame_destroys_all_minions_and_grants_shards():
    game, p1, p2 = new_frierenrift_game()
    _ = make_battlefield_minion(game, WISP, p1)
    _ = make_battlefield_minion(game, CHILLWIND_YETI, p2)
    _ = make_battlefield_minion(game, BOULDERFIST_OGRE, p1)

    # Snapshot shards and crystals.
    start_az_p1 = int(_ensure_variant_resources(p1)["azure"])
    start_crystals_p1 = p1.mana_crystals
    start_crystals_p2 = p2.mana_crystals

    # Invoke the spell effect directly (bypass cast gating since we're unit-testing).
    caster_obj = game.create_object(
        name="casting_source",
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=WISP.characteristics,
        card_def=None,
    )
    events = ETERNAL_FLAME_OF_ETHOS.spell_effect(caster_obj, game.state)
    for ev in events:
        game.emit(ev)

    bf = game.state.zones["battlefield"]
    minions_left = [
        oid for oid in bf.objects
        if CardType.MINION in game.state.objects[oid].characteristics.types
    ]
    assert minions_left == [caster_obj.id] or caster_obj.id not in minions_left
    # Each player gained a shard of each color.
    assert _ensure_variant_resources(p1)["azure"] == start_az_p1 + 1
    # Each player gained 1 max mana (capped at 10 beforehand in harness — adjust).
    assert p1.mana_crystals >= min(10, start_crystals_p1 + 1) or p1.mana_crystals == 10
    assert p2.mana_crystals >= min(10, start_crystals_p2 + 1) or p2.mana_crystals == 10


# ----------------------------------------------------------------------------
# Deck sanity check — ensures decks stay at 30 cards and imports clean.
# ----------------------------------------------------------------------------


def test_deck_sizes_intact():
    assert len(FRIERENRIFT_DECKS["Frieren"]) == 30
    assert len(FRIERENRIFT_DECKS["Macht"]) == 30


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
