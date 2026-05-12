"""Depth-pass coverage for Beyond Kamigawa Yu-Gi-Oh! cards."""

from src.cards.yugioh.beyond.kamigawa import BEYOND_KAMIGAWA_CARDS
from src.cards.yugioh.beyond.kamigawa.ninja import (
    SEALING_TAG,
    NINJA_OF_THE_DEEP_HOURS,
    PATH_OF_THE_SHADOW,
)
from src.cards.yugioh.beyond.kamigawa.moonfolk import (
    REFLECT_LORD,
    SORATAMI_SAVANT,
)
from src.cards.yugioh.beyond.kamigawa.samurai import (
    EIGANJO_CASTLE,
    HAND_OF_HONOR,
    ISAMARU_HOUND_OF_KONDA,
    KITSUNE_TSUKI,
    KONDAS_BANNER_BEARER,
    PATH_OF_BRAVERY,
    RONIN_HOUNDMASTER,
)
from src.cards.yugioh.beyond.kamigawa.spirit_dragons import (
    TIDESHEPHERD_KOI_SPIRIT,
    VILLAGE_GUIDE_SPIRIT,
)
from src.cards.yugioh.beyond.kamigawa.staples import (
    ARGENTUM_ARMOR,
    HONDEN_OF_SEEING_WINDS,
    PLAINS,
    SPELL_PIERCE,
    STONEFORGE_MYSTIC,
)
from src.engine.game import Game, make_ygo_monster
from src.engine.queries import get_power, get_toughness, has_ability
from src.engine.types import Event, EventStatus, EventType, ZoneType
from src.engine.yugioh_spells import YugiohSpellTrapManager
from scripts.play.custom_set_depth_report import card_depth, summarize_set


DEPTH_PASS_UPGRADES = {
    "Argentum Armor",
    "Boseiju, Who Shelters All",
    "Coiled Tomb",
    "Eiganjo Castle",
    "Force Spike",
    "Karma",
    "Mirror Realm",
    "Negate",
    "Solitary Confinement",
    "Spell Pierce",
    "Stoneforge Mystic",
    "Tideshepherd Koi Spirit",
}

PASS2_DEPTH_UPGRADES = {
    "Awakening Hour",
    "Boseiju, Who Shelters All",
    "Cancel",
    "Cloak and Dagger",
    "Counterspell, Lite Edition",
    "Dark Ritual",
    "Day of Judgment",
    "Demonic Tutor",
    "Doom Blade",
    "Fact or Fiction",
    "Final Word",
    "Force Spike",
    "Forest, Whispering Glade",
    "Hinder",
    "Honden of Cleansing Fire",
    "Honden of Infinite Rage",
    "Honden of Life's Web",
    "Honden of Night's Reach",
    "Honden of Seeing Winds",
    "Howling Mine",
    "Island, Mirror's Edge",
    "Lightning Bolt",
    "Mountain, Smoldering Crag",
    "Negate",
    "Ninja Strike Force",
    "Ninja's Cunning",
    "Path of Bravery",
    "Path of the Shadow",
    "Path to Exile",
    "Plains, Sanctified Ground",
    "Reach Through Mists",
    "Reality Stutter",
    "Solemn Wayfarer",
    "Spell Pierce",
    "Swamp, Choking Mire",
    "Sword and Shield",
    "Swords to Plowshares",
    "Wandering Negation",
    "Wheel of Fortune",
    "Wrath of God",
}

PASS3_DEPTH_UPGRADES = {
    "Akki Coalflinger",
    "Auto-Repair Module",
    "Boseiju's Reach",
    "Brainstorm",
    "Brothers Yamazaki",
    "Bushido Honor",
    "Charge of the Five Stars",
    "Cleaving Reach",
    "Cogwork Ambush",
    "Cranial Plating",
    "Cyber Salvage",
    "Cyber-Spirit Conduit",
    "Daimyo's Spirit Steed",
    "Devouring Greed",
    "Empyrial Plate",
    "Eye of Nowhere",
    "Final Flourish",
    "Final Smoke",
    "General Fumiko",
    "Hana Kami",
    "Hand of Cruelty",
    "Hand of Honor",
    "Heavy Boots",
    "Heroic Sacrifice",
    "Hikari, Twilight Guardian",
    "Honor-Worn Shaku",
    "Imperial Edict",
    "Imperial Mobilization",
    "Iname, Death Aspect",
    "Iname, Life Aspect",
    "Isamaru, Hound of Konda",
    "Kami of Hopeful Strength",
    "Karma",
    "Konda's Hatamoto",
    "Kotori, the Pearl-Shell Dragon",
    "Lightning Greaves",
    "Mana Leak",
    "Mirror Stone of Five Suns",
    "Mistblade's Cunning",
    "Ninja Grandmaster Sasuke",
    "Ninjitsu Art of Decoy",
    "Ninjitsu Art of Duplication",
    "Ninjitsu Art of Transformation",
    "Otherworldly Journey",
    "Reality Chip Bearer",
    "Reciprocate",
    "Refurbish",
    "Reverberate",
    "Saheeli, the Gifted",
    "Sangromancer",
    "Smoke Bomb",
    "Soratami Savant",
    "Soulless Ringing",
    "Splice Bushido",
    "Spirit Bond",
    "Squee, Goblin Nabob",
    "Stand Together",
    "Tezzeret's Edict",
    "The Reality Chip",
    "The Wandering Decree",
    "The Wandering Emperor, Modified Variant",
    "The Wandering Heir",
    "Tide of Knowledge",
    "Trial of the Moonless Night",
    "Vapor Snag",
    "Village Guide Spirit",
    "Voltron Construct",
    "Whispersilk Cloak",
    "Workshop Assembly",
    "Yukora, the Prisoner",
}


def _new_game():
    game = Game(mode="yugioh")
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    game.setup_yugioh_player(p1, [], [])
    game.setup_yugioh_player(p2, [], [])
    return game, p1, p2


def _card(game: Game, card_def, owner, zone: ZoneType):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _face_up_monster(game: Game, owner, card_def):
    obj = _card(game, card_def, owner, ZoneType.MONSTER_ZONE)
    obj.state.face_down = False
    obj.state.ygo_position = "face_up_atk"
    return obj


def _query_atk(game: Game, monster) -> int:
    monster.characteristics.power = getattr(monster.card_def, "atk", 0) or 0
    return get_power(monster, game.state)


def _query_def(game: Game, monster) -> int:
    monster.characteristics.toughness = getattr(monster.card_def, "def_val", 0) or 0
    return get_toughness(monster, game.state)


def test_stoneforge_mystic_searches_and_equips_from_hand():
    game, p1, _p2 = _new_game()
    mystic = _face_up_monster(game, p1, STONEFORGE_MYSTIC)
    armor = _card(game, ARGENTUM_ARMOR, p1, ZoneType.LIBRARY)

    game.emit(Event(
        type=EventType.YGO_NORMAL_SUMMON,
        payload={"player": p1.id, "card_id": mystic.id},
    ))

    assert armor.zone == ZoneType.HAND

    events = game.emit(Event(
        type=EventType.ACTIVATE,
        payload={"player": p1.id, "card_id": mystic.id},
    ))

    assert armor.zone == ZoneType.SPELL_TRAP_ZONE
    assert armor.state.equipped_to == mystic.id
    assert any(event.type == EventType.YGO_EQUIP for event in events)


def test_tideshepherd_tributes_spirit_to_special_summon_from_hand():
    game, p1, _p2 = _new_game()
    fodder = _face_up_monster(game, p1, VILLAGE_GUIDE_SPIRIT)
    koi = _card(game, TIDESHEPHERD_KOI_SPIRIT, p1, ZoneType.HAND)

    events = game.emit(Event(
        type=EventType.ACTIVATE,
        payload={"player": p1.id, "card_id": koi.id},
    ))

    assert fodder.zone == ZoneType.GRAVEYARD
    assert koi.zone == ZoneType.MONSTER_ZONE
    assert any(
        event.type == EventType.YGO_SPECIAL_SUMMON
        and event.payload.get("summon_type") == "tideshepherd"
        for event in events
    )


def test_eiganjo_castle_boosts_and_prevents_first_battle_destroy():
    game, p1, _p2 = _new_game()
    spell_mgr = YugiohSpellTrapManager(game.state)
    castle = _card(game, EIGANJO_CASTLE, p1, ZoneType.HAND)
    samurai = _face_up_monster(game, p1, HAND_OF_HONOR)
    game.state.turn_number = 4

    spell_mgr.activate_spell(castle.id, p1.id)

    assert castle.zone == ZoneType.FIELD_SPELL_ZONE
    assert _query_atk(game, samurai) == HAND_OF_HONOR.atk + 200

    first = game.emit(Event(
        type=EventType.YGO_DESTROY,
        payload={"card_id": samurai.id, "reason": "battle"},
    ))[0]
    second = game.emit(Event(
        type=EventType.YGO_DESTROY,
        payload={"card_id": samurai.id, "reason": "battle"},
    ))[0]

    assert first.status == EventStatus.PREVENTED
    assert second.status != EventStatus.PREVENTED


def test_spell_pierce_taxes_when_possible_and_negates_when_not():
    game, p1, p2 = _new_game()
    spell_mgr = YugiohSpellTrapManager(game.state)
    pierce = _card(game, SPELL_PIERCE, p1, ZoneType.SPELL_TRAP_ZONE)
    pierce.state.face_down = True
    pierce.state.turns_set = 1
    p2.lp = 8000

    tax_events = spell_mgr.activate_trap(pierce.id, p1.id)

    assert p2.lp == 6000
    assert any(event.type == EventType.YGO_LP_CHANGE for event in tax_events)

    pierce_2 = _card(game, SPELL_PIERCE, p1, ZoneType.SPELL_TRAP_ZONE)
    pierce_2.state.face_down = True
    pierce_2.state.turns_set = 1
    p2.lp = 1500

    negate_events = spell_mgr.activate_trap(pierce_2.id, p1.id)

    assert any(
        event.type == EventType.YGO_CHAIN_LINK
        and event.payload.get("effect") == "negate_spell_unless_pay"
        for event in negate_events
    )


def test_argentum_armor_attack_trigger_destroys_face_up_card():
    game, p1, p2 = _new_game()
    attacker = _face_up_monster(game, p1, make_ygo_monster("Equipped Attacker", 1000, 1000))
    armor = _card(game, ARGENTUM_ARMOR, p1, ZoneType.SPELL_TRAP_ZONE)
    target = _face_up_monster(game, p2, make_ygo_monster("Target", 1800, 1200))
    armor.state.equipped_to = attacker.id

    events = game.emit(Event(
        type=EventType.YGO_BATTLE_DECLARE,
        payload={"attacker_id": attacker.id, "target_id": target.id},
    ))

    assert target.zone == ZoneType.GRAVEYARD
    assert any(event.type == EventType.YGO_DESTROY for event in events)


def test_honden_field_spell_repeats_on_controller_standby():
    game, p1, _p2 = _new_game()
    spell_mgr = YugiohSpellTrapManager(game.state)
    honden = _card(game, HONDEN_OF_SEEING_WINDS, p1, ZoneType.HAND)
    draw_1 = _card(game, make_ygo_monster("Draw One", 100, 100), p1, ZoneType.LIBRARY)
    draw_2 = _card(game, make_ygo_monster("Draw Two", 100, 100), p1, ZoneType.LIBRARY)

    spell_mgr.activate_spell(honden.id, p1.id)

    assert honden.zone == ZoneType.FIELD_SPELL_ZONE
    assert draw_1.zone == ZoneType.HAND

    game.state.turn_number = 3
    events = game.emit(Event(
        type=EventType.PHASE_CHANGE,
        payload={"player": p1.id, "phase": "standby"},
    ))

    assert draw_2.zone == ZoneType.HAND
    assert any(event.type == EventType.YGO_DRAW for event in events)


def test_attribute_field_spell_boosts_matching_attributes_only():
    game, p1, _p2 = _new_game()
    spell_mgr = YugiohSpellTrapManager(game.state)
    plains = _card(game, PLAINS, p1, ZoneType.HAND)
    light_monster = _face_up_monster(
        game, p1,
        make_ygo_monster("Light Soldier", 1000, 1000, attribute="LIGHT"),
    )
    water_monster = _face_up_monster(
        game, p1,
        make_ygo_monster("Water Soldier", 1000, 1000, attribute="WATER"),
    )

    spell_mgr.activate_spell(plains.id, p1.id)

    assert _query_atk(game, light_monster) == 1200
    assert _query_def(game, light_monster) == 1200
    assert _query_atk(game, water_monster) == 1000


def test_path_of_bravery_tracks_samurai_normal_summons():
    game, p1, _p2 = _new_game()
    spell_mgr = YugiohSpellTrapManager(game.state)
    path = _card(game, PATH_OF_BRAVERY, p1, ZoneType.HAND)
    samurai = _face_up_monster(game, p1, HAND_OF_HONOR)

    spell_mgr.activate_spell(path.id, p1.id)
    game.emit(Event(
        type=EventType.YGO_NORMAL_SUMMON,
        payload={"player": p1.id, "card_id": samurai.id},
    ))

    assert _query_atk(game, samurai) == HAND_OF_HONOR.atk + 200


def test_path_of_the_shadow_grants_pierce_to_ninjas():
    game, p1, _p2 = _new_game()
    spell_mgr = YugiohSpellTrapManager(game.state)
    path = _card(game, PATH_OF_THE_SHADOW, p1, ZoneType.HAND)
    ninja = _face_up_monster(game, p1, NINJA_OF_THE_DEEP_HOURS)

    spell_mgr.activate_spell(path.id, p1.id)

    assert has_ability(ninja, "pierce", game.state)


def test_pass3_team_lords_boost_other_archetype_members_only():
    game, p1, _p2 = _new_game()
    banner = _face_up_monster(game, p1, KONDAS_BANNER_BEARER)
    samurai = _face_up_monster(
        game, p1,
        make_ygo_monster(
            "Plain Samurai", 1000, 1000,
            subtypes={"Warrior", "Samurai"},
        ),
    )

    assert _query_atk(game, samurai) == 1200
    assert _query_atk(game, banner) == KONDAS_BANNER_BEARER.atk

    reflect = _face_up_monster(game, p1, REFLECT_LORD)
    savant = _face_up_monster(
        game, p1,
        make_ygo_monster(
            "Plain Moonfolk", 1000, 1000,
            subtypes={"Spellcaster", "Moonfolk"},
        ),
    )

    assert _query_atk(game, savant) == 1200
    assert _query_atk(game, reflect) == REFLECT_LORD.atk


def test_pass3_small_samurai_and_spirit_glue_searches_and_protects():
    game, p1, _p2 = _new_game()
    isamaru = _face_up_monster(game, p1, ISAMARU_HOUND_OF_KONDA)
    ally = _face_up_monster(game, p1, HAND_OF_HONOR)
    ronin = _face_up_monster(game, p1, RONIN_HOUNDMASTER)
    recruit = _card(game, ISAMARU_HOUND_OF_KONDA, p1, ZoneType.LIBRARY)
    guide = _face_up_monster(game, p1, VILLAGE_GUIDE_SPIRIT)
    koi = _card(game, TIDESHEPHERD_KOI_SPIRIT, p1, ZoneType.LIBRARY)
    game.state.turn_number = 9

    assert _query_atk(game, isamaru) == ISAMARU_HOUND_OF_KONDA.atk + 400

    first = game.emit(Event(
        type=EventType.YGO_DESTROY,
        payload={"card_id": isamaru.id, "reason": "battle"},
    ))[0]
    second = game.emit(Event(
        type=EventType.YGO_DESTROY,
        payload={"card_id": isamaru.id, "reason": "battle"},
    ))[0]

    assert first.status == EventStatus.PREVENTED
    assert second.status != EventStatus.PREVENTED

    game.emit(Event(
        type=EventType.YGO_NORMAL_SUMMON,
        payload={"player": p1.id, "card_id": ronin.id},
    ))
    game.emit(Event(
        type=EventType.YGO_NORMAL_SUMMON,
        payload={"player": p1.id, "card_id": guide.id},
    ))

    assert recruit.zone == ZoneType.HAND
    assert koi.zone == ZoneType.HAND
    assert ally.zone == ZoneType.MONSTER_ZONE


def test_pass3_level_seals_mark_large_opposing_monsters():
    game, p1, p2 = _new_game()
    spell_mgr = YugiohSpellTrapManager(game.state)
    tsuki = _card(game, KITSUNE_TSUKI, p1, ZoneType.SPELL_TRAP_ZONE)
    tsuki.state.face_down = True
    tsuki.state.turns_set = 1
    large = _face_up_monster(
        game, p2,
        make_ygo_monster("Large Effect", 2200, 1800, level=6),
    )
    small = _face_up_monster(
        game, p2,
        make_ygo_monster("Small Effect", 1200, 1000, level=4),
    )

    spell_mgr.activate_trap(tsuki.id, p1.id)

    assert has_ability(large, "effects_negated", game.state)
    assert not has_ability(small, "effects_negated", game.state)

    game2, q1, q2 = _new_game()
    spell_mgr2 = YugiohSpellTrapManager(game2.state)
    tag = _card(game2, SEALING_TAG, q1, ZoneType.SPELL_TRAP_ZONE)
    tag.state.face_down = True
    tag.state.turns_set = 1
    boss = _face_up_monster(
        game2, q2,
        make_ygo_monster("Tagged Boss", 2500, 2000, level=7),
    )

    spell_mgr2.activate_trap(tag.id, q1.id)

    assert has_ability(boss, "effects_negated", game2.state)


def test_beyond_kamigawa_depth_gate_counts_behavior_hooks():
    hooked = {
        name for name, card in BEYOND_KAMIGAWA_CARDS.items()
        if card.setup_interceptors or card.resolve
    }

    assert len(hooked) >= 240
    assert DEPTH_PASS_UPGRADES <= hooked
    assert len(PASS2_DEPTH_UPGRADES) == 40
    assert PASS2_DEPTH_UPGRADES <= hooked
    assert len(PASS3_DEPTH_UPGRADES) == 70
    assert PASS3_DEPTH_UPGRADES <= hooked

    summary = summarize_set(list(BEYOND_KAMIGAWA_CARDS.values()))
    assert summary["avg_score"] >= 51.0
    assert summary["thin_count"] == 0
    assert summary["wired_pct"] >= 74.0
    assert all(
        card_depth(BEYOND_KAMIGAWA_CARDS[name])["score"] >= 28
        for name in PASS2_DEPTH_UPGRADES
    )
    assert all(
        card_depth(BEYOND_KAMIGAWA_CARDS[name])["score"] >= 40
        for name in PASS3_DEPTH_UPGRADES
    )

    interaction_terms = (
        "destroy", "negate", "return", "special summon", "ss ",
        "equip", "draw", "lp", "battle", "gain", "search",
        "banish", "chain", "standby", "tribute", "field",
        "change", "shuffle", "reveal", "swap", "layer",
        "trigger", "marker", "prevent",
    )
    assert all(
        any(term in (BEYOND_KAMIGAWA_CARDS[name].text or "").lower()
            for term in interaction_terms)
        for name in DEPTH_PASS_UPGRADES | PASS2_DEPTH_UPGRADES | PASS3_DEPTH_UPGRADES
    )
