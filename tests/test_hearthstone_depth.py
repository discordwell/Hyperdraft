"""Focused depth-pass tests for Stormrift Hearthstone cards."""

from scripts.play.custom_set_depth_report import card_depth, summarize_set
from src.engine.game import Game
from src.engine.types import Event, EventType, ZoneType, CardType
from src.cards.hearthstone import frierenrift, riftclash, stormrift
from src.cards.hearthstone.stormrift import (
    GLACIAL_SENTINEL,
    FROZEN_REVENANT,
    GLACIEL_HERO,
    FROST_RIFT,
    IGNIS_HERO,
    NEXUS_GUARDIAN,
    PYROCLASM_ADEPT,
    RIFT_BOLT,
    RIFT_IMP,
    RIFT_SPARK,
    RIFT_SPARK_ELEMENTAL,
    STORM_ACOLYTE,
    STORM_HERALD,
)


UPGRADED_STORMRIFT_CARDS = {
    "Rift Spark Elemental",
    "Kindling Imp",
    "Singe",
    "Storm Acolyte",
    "Rift Bolt",
    "Rift Firehound",
    "Pyroclasm Adept",
    "Pyroclasm Drake",
    "Searing Rift",
    "Inferno Golem",
    "Inferno Wave",
    "Pyroclasm",
    "Rift Walker",
    "Frost Wisp",
    "Void Sprite",
    "Glacial Sentinel",
    "Void Seer",
    "Frozen Revenant",
    "Abyssal Lurker",
    "Voidcrystal Golem",
    "Blizzard Golem",
    "Void Anchor",
    "Rift Guardian",
    "Rift Sight",
    "Void Barrier",
    "Void Drain",
    "Storm Herald",
    "Rift Imp",
    "Nexus Guardian",
    "Rift Champion",
    "Rift Behemoth",
}

UPGRADED_FRIERENRIFT_CARDS = {
    "Apprentice Caster",
    "Stark, Vanguard Guardian",
    "Flight Magic Circle",
    "Grimoire Archive",
    "Fern's Follow-Up",
    "Journey to Aureole",
    "Supplicant Adept",
    "Macht's Gold Guard",
    "Demon Suppression",
    "El Dorado Collapse",
    "Qual's Venom Lance",
    "Severing Guillotine",
    "Fearsome Battalion",
}

UPGRADED_RIFTCLASH_CARDS = {
    "Ice Shackle",
    "Glacial Insight",
}

PASS3_HEARTHSTONE_CARDS = {
    "Absolute Archivist",
    "Apprentice Caster",
    "Aureole Wayfinder",
    "Aura Severing Ray",
    "Blizzard Golem",
    "Canon of Souls",
    "Chain Lightning",
    "Cinder Lance",
    "Cryo Sentinel",
    "Draht, Binding Thread",
    "Ember Channeler",
    "Ember Volley, Unchained",
    "Fern's Follow-Up",
    "Fern, Precise Disciple",
    "Frost Spike",
    "Glacial Insight",
    "Glacial Sentinel",
    "Glacial Tomb",
    "Ignis Ascendant",
    "Inferno Wave",
    "Journey to Aureole",
    "Kraft, Roadside Monk",
    "Linie, Perfect Copy",
    "Macht's Gold Guard",
    "Pyroclasm",
    "Pyroclasm Adept",
    "Pyroclasm Drake",
    "Rift Behemoth",
    "Rift Berserker",
    "Rift Firehound",
    "Rift Sight",
    "Rift Walker",
    "Rift Watcher",
    "Searing Rift",
    "Storm Acolyte",
    "Storm Herald",
    "Void Barrier",
    "Voidcrystal Golem",
    "Voidfrost Dragon",
    "Volatilerift Mage",
}

UPGRADED_HEARTHSTONE_CARDS = (
    UPGRADED_STORMRIFT_CARDS
    | UPGRADED_FRIERENRIFT_CARDS
    | UPGRADED_RIFTCLASH_CARDS
)


def make_hs_game():
    game = Game(mode="hearthstone")
    p1 = game.add_player("P1", life=30)
    p2 = game.add_player("P2", life=30)
    game.setup_hearthstone_player(p1, IGNIS_HERO, RIFT_SPARK)
    game.setup_hearthstone_player(p2, GLACIEL_HERO, FROST_RIFT)
    return game, p1, p2


def make_frieren_game():
    game = Game(mode="hearthstone")
    p1 = game.add_player("Frieren", life=30)
    p2 = game.add_player("Macht", life=30)
    game.setup_hearthstone_player(p1, frierenrift.FRIEREN_HERO, frierenrift.ANALYZE_FORMULA)
    game.setup_hearthstone_player(p2, frierenrift.MACHT_HERO, frierenrift.GOLD_HEX)
    return game, p1, p2


def make_riftclash_game():
    game = Game(mode="hearthstone")
    p1 = game.add_player("Pyro", life=30)
    p2 = game.add_player("Cryo", life=30)
    game.setup_hearthstone_player(p1, riftclash.IGNIS_REFORGED, riftclash.EMBER_VOLLEY)
    game.setup_hearthstone_player(p2, riftclash.GLACIEL_REFORGED, riftclash.CRYO_WARD)
    return game, p1, p2


def spawn(game, card_def, owner_id):
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def spell_object(game, card_def, owner_id):
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.STACK,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def test_storm_herald_boosts_next_spell_once():
    game, p1, p2 = make_hs_game()
    herald = spawn(game, STORM_HERALD, p1.id)
    STORM_HERALD.battlecry(herald, game.state)

    first = spell_object(game, RIFT_BOLT, p1.id)
    before = p2.life
    game.pipeline.emit(Event(
        type=EventType.SPELL_CAST,
        payload={"caster": p1.id},
        source=first.id,
        controller=p1.id,
    ))
    for event in RIFT_BOLT.spell_effect(first, game.state, []):
        game.pipeline.emit(event)

    assert before - p2.life == 4

    second = spell_object(game, RIFT_BOLT, p1.id)
    before_second = p2.life
    game.pipeline.emit(Event(
        type=EventType.SPELL_CAST,
        payload={"caster": p1.id},
        source=second.id,
        controller=p1.id,
    ))
    for event in RIFT_BOLT.spell_effect(second, game.state, []):
        game.pipeline.emit(event)

    assert before_second - p2.life == 3


def test_pyroclasm_adept_battlecry_requires_prior_spell():
    game, p1, _p2 = make_hs_game()
    adept = spawn(game, PYROCLASM_ADEPT, p1.id)

    fallback = PYROCLASM_ADEPT.battlecry(adept, game.state)
    assert fallback[0].type == EventType.ARMOR_GAIN
    assert fallback[0].payload == {"player": p1.id, "amount": 1}

    spell = spell_object(game, RIFT_BOLT, p1.id)
    game.pipeline.emit(Event(
        type=EventType.SPELL_CAST,
        payload={"caster": p1.id},
        source=spell.id,
        controller=p1.id,
    ))

    events = PYROCLASM_ADEPT.battlecry(adept, game.state)

    assert len(events) == 1
    assert events[0].type == EventType.DAMAGE
    assert events[0].payload["amount"] == 2


def test_volatilerift_mage_turns_damaged_board_into_armor():
    game, p1, p2 = make_hs_game()
    spawn(game, stormrift.VOLATILERIFT_MAGE, p1.id)
    enemy = spawn(game, RIFT_IMP, p2.id)
    enemy.state.damage = 1

    spell = spell_object(game, RIFT_BOLT, p1.id)
    game.pipeline.emit(Event(
        type=EventType.SPELL_CAST,
        payload={"caster": p1.id},
        source=spell.id,
        controller=p1.id,
    ))

    assert p1.armor == 1
    assert enemy.state.damage == 2


def test_storm_acolyte_gains_armor_only_on_first_spell_each_turn():
    game, p1, _p2 = make_hs_game()
    spawn(game, STORM_ACOLYTE, p1.id)

    first = spell_object(game, RIFT_BOLT, p1.id)
    game.pipeline.emit(Event(
        type=EventType.SPELL_CAST,
        payload={"caster": p1.id},
        source=first.id,
        controller=p1.id,
    ))
    assert p1.armor == 1

    second = spell_object(game, RIFT_BOLT, p1.id)
    game.pipeline.emit(Event(
        type=EventType.SPELL_CAST,
        payload={"caster": p1.id},
        source=second.id,
        controller=p1.id,
    ))
    assert p1.armor == 1


def test_rift_spark_elemental_backfires_unless_rift_storm_killed_it():
    game, p1, _p2 = make_hs_game()
    spark = spawn(game, RIFT_SPARK_ELEMENTAL, p1.id)

    backfire = RIFT_SPARK_ELEMENTAL.deathrattle(spark, game.state)
    assert backfire[0].payload["target"] == p1.hero_id

    spark.state.last_damage_source = "rift_storm"
    redirected = RIFT_SPARK_ELEMENTAL.deathrattle(spark, game.state)
    assert redirected[0].payload["target"] != p1.hero_id
    assert redirected[0].payload["amount"] == 1


def test_nexus_guardian_armor_requires_another_elemental():
    game, p1, _p2 = make_hs_game()
    guardian = spawn(game, NEXUS_GUARDIAN, p1.id)

    assert NEXUS_GUARDIAN.battlecry(guardian, game.state) == []

    spawn(game, GLACIAL_SENTINEL, p1.id)
    events = NEXUS_GUARDIAN.battlecry(guardian, game.state)
    assert events[0].type == EventType.ARMOR_GAIN
    assert events[0].payload == {"player": p1.id, "amount": 2}


def test_rift_imp_splits_into_extra_spark_when_storm_killed():
    game, p1, _p2 = make_hs_game()
    imp = spawn(game, RIFT_IMP, p1.id)
    imp.state.last_damage_source = "rift_storm"

    events = RIFT_IMP.deathrattle(imp, game.state)

    assert len(events) == 1
    token_event = events[0]
    assert token_event.type == EventType.CREATE_TOKEN
    assert token_event.payload["count"] == 2
    assert token_event.payload["token"]["name"] == "Rift Spark"


def test_frozen_revenant_converts_damage_into_freeze_and_armor():
    game, p1, p2 = make_hs_game()
    damaged_enemy = spawn(game, RIFT_IMP, p1.id)
    damaged_enemy.state.damage = 1
    revenant = spawn(game, FROZEN_REVENANT, p2.id)

    events = FROZEN_REVENANT.deathrattle(revenant, game.state)

    assert any(
        event.type == EventType.FREEZE_TARGET
        and event.payload["target"] == damaged_enemy.id
        for event in events
    )
    assert any(
        event.type == EventType.ARMOR_GAIN
        and event.payload["player"] == p2.id
        and event.payload["amount"] == 1
        for event in events
    )


def test_frierenrift_shard_and_control_riders():
    game, p1, p2 = make_frieren_game()

    apprentice = spawn(game, frierenrift.APPRENTICE_CASTER, p1.id)
    frierenrift.APPRENTICE_CASTER.battlecry(apprentice, game.state)
    assert p1.variant_resources["azure"] == 1

    p1.variant_resources = {"azure": 1, "ember": 1, "verdant": 1}
    flight = spell_object(game, frierenrift.FLIGHT_MAGIC_CIRCLE, p1.id)
    token_events = frierenrift.FLIGHT_MAGIC_CIRCLE.spell_effect(flight, game.state, [])
    assert len(token_events) == 2
    assert all(
        {"keyword": "taunt"} in event.payload["token"]["abilities"]
        for event in token_events
    )

    enemy = spawn(game, frierenrift.MACHT_GOLD_GUARD, p2.id)
    venom = spell_object(game, frierenrift.QUAL_VENOM_LANCE, p1.id)
    events = frierenrift.QUAL_VENOM_LANCE.spell_effect(venom, game.state, [])
    assert any(event.type == EventType.DAMAGE and event.payload["target"] == enemy.id for event in events)
    assert any(event.type == EventType.FREEZE_TARGET and event.payload["target"] == enemy.id for event in events)


def test_frierenrift_low_curve_spells_gain_complete_shard_riders():
    game, p1, p2 = make_frieren_game()
    p1.variant_resources = {"azure": 1, "ember": 1, "verdant": 1}
    enemy = spawn(game, stormrift.NEXUS_GUARDIAN, p2.id)

    benediction = spell_object(game, frierenrift.HEITER_BENEDICTION, p1.id)
    benediction_events = frierenrift.HEITER_BENEDICTION.spell_effect(benediction, game.state, [])
    assert any(event.type == EventType.FREEZE_TARGET and event.payload["target"] == enemy.id for event in benediction_events)
    assert sum(
        event.payload["amount"]
        for event in benediction_events
        if event.type == EventType.ARMOR_GAIN and event.payload["player"] == p1.id
    ) == 4

    curse = spell_object(game, frierenrift.GOLD_CURSE, p1.id)
    curse_events = frierenrift.GOLD_CURSE.spell_effect(curse, game.state, [])
    assert any(
        event.type == EventType.DAMAGE
        and event.payload["target"] == enemy.id
        and event.payload["amount"] == 1
        for event in curse_events
    )
    assert any(event.type == EventType.DRAW and event.payload["player"] == p1.id for event in curse_events)


def test_frierenrift_pass3_shard_completion_and_frozen_payoffs():
    game, p1, p2 = make_frieren_game()

    p1.variant_resources = {"azure": 1, "ember": 1, "verdant": 0}
    wayfinder = spawn(game, frierenrift.AUREOLE_WAYFINDER, p1.id)
    wayfinder_events = frierenrift.AUREOLE_WAYFINDER.battlecry(wayfinder, game.state)
    assert p1.variant_resources == {"azure": 1, "ember": 1, "verdant": 1}
    assert wayfinder_events == []

    enemy = spawn(game, stormrift.NEXUS_GUARDIAN, p2.id)
    enemy.state.frozen = True
    draht = spawn(game, frierenrift.DRAHT_BINDING_THREAD, p1.id)
    draht_events = frierenrift.DRAHT_BINDING_THREAD.battlecry(draht, game.state)
    assert any(event.type == EventType.FREEZE_TARGET and event.payload["target"] == enemy.id for event in draht_events)
    assert any(event.type == EventType.DRAW for event in draht_events)


def test_frierenrift_guillotine_converts_attack_to_armor():
    game, p1, p2 = make_frieren_game()
    enemy = spawn(game, frierenrift.FEARSOME_BATTALION, p2.id)
    guillotine = spell_object(game, frierenrift.SEVERING_GUILLOTINE, p1.id)

    events = frierenrift.SEVERING_GUILLOTINE.spell_effect(guillotine, game.state, [])

    assert any(
        event.type == EventType.OBJECT_DESTROYED
        and event.payload["object_id"] == enemy.id
        for event in events
    )
    assert any(
        event.type == EventType.ARMOR_GAIN
        and event.payload["player"] == p1.id
        and event.payload["amount"] == 3
        for event in events
    )


def test_riftclash_freeze_riders_draw_and_scale_armor():
    game, p1, p2 = make_riftclash_game()
    enemy = spawn(game, NEXUS_GUARDIAN, p2.id)
    enemy.state.frozen = True

    shackle = spell_object(game, riftclash.ICE_SHACKLE, p1.id)
    shackle_events = riftclash.ICE_SHACKLE.spell_effect(shackle, game.state, [])
    assert any(event.type == EventType.DRAW and event.payload["player"] == p1.id for event in shackle_events)

    insight = spell_object(game, riftclash.GLACIAL_INSIGHT, p1.id)
    insight_events = riftclash.GLACIAL_INSIGHT.spell_effect(insight, game.state, [])
    assert any(
        event.type == EventType.ARMOR_GAIN
        and event.payload["amount"] == 3
        for event in insight_events
    )


def test_riftclash_pass3_cinder_lance_and_cryo_sentinel_branches():
    game, p1, p2 = make_riftclash_game()
    enemy = spawn(game, NEXUS_GUARDIAN, p2.id)
    enemy.state.damage = 3

    lance = spell_object(game, riftclash.CINDER_LANCE, p1.id)
    lance_events = riftclash.CINDER_LANCE.spell_effect(lance, game.state, [])
    assert any(
        event.type == EventType.ADD_TO_HAND
        and event.payload["card_def"].name == "Cinder Charge"
        for event in lance_events
    )

    enemy.state.frozen = True
    sentinel = spawn(game, riftclash.CRYO_SENTINEL, p1.id)
    sentinel_events = riftclash.CRYO_SENTINEL.deathrattle(sentinel, game.state)
    assert any(event.type == EventType.FREEZE_TARGET for event in sentinel_events)
    assert any(event.type == EventType.DRAW for event in sentinel_events)


def _hearthstone_custom_cards():
    cards = []
    for deck_map in (stormrift.STORMRIFT_DECKS, frierenrift.FRIERENRIFT_DECKS, riftclash.RIFTCLASH_DECKS):
        for deck in deck_map.values():
            cards.extend(deck)

    seen = set()
    unique = []
    for card in cards:
        if id(card) in seen:
            continue
        seen.add(id(card))
        unique.append(card)
    return unique


def _hearthstone_module_cards():
    cards = []
    for module in (stormrift, frierenrift, riftclash):
        for value in vars(module).values():
            if not hasattr(value, "characteristics"):
                continue
            types = value.characteristics.types if value.characteristics else set()
            if CardType.MINION in types or CardType.SPELL in types:
                cards.append(value)
    return cards


def test_hearthstone_depth_gate_eliminates_thin_custom_cards():
    cards = _hearthstone_custom_cards()
    upgraded = {card.name: card for card in _hearthstone_module_cards() if card.name in UPGRADED_HEARTHSTONE_CARDS}
    assert set(upgraded) == UPGRADED_HEARTHSTONE_CARDS
    assert all(
        card.battlecry or card.deathrattle or card.setup_interceptors or card.spell_effect
        for card in upgraded.values()
    )
    assert all(card_depth(card)["score"] >= 28 for card in upgraded.values())

    summary = summarize_set(cards)
    assert summary["thin_count"] == 0
    assert summary["avg_score"] >= 50
    assert summary["wired_pct"] == 100.0


def test_hearthstone_pass3_lifted_cards_reach_mid_depth():
    upgraded = {card.name: card for card in _hearthstone_module_cards() if card.name in PASS3_HEARTHSTONE_CARDS}
    assert set(upgraded) == PASS3_HEARTHSTONE_CARDS
    assert len(upgraded) == 40
    assert all(card_depth(card)["score"] >= 45 for card in upgraded.values())
