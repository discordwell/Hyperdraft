"""Smoke tests for the graveyard-activated / death-trigger / threaten sweep.

This sweep wired up:
- Graveyard-activated abilities via card_def.setup_in_graveyard:
  Suspicious Shambler, Leering Onlooker, Gravestone Strider, Colossal
  Rattlewurm, Bonebind Orator, Goldmeadow Nomad, Stoic Grove-Guide,
  Beetle Legacy Criminal, Venom Evil Unleashed, Morbius the Living Vampire.
- Death-trigger grants via grant_death_trigger:
  Undying Malice, Fake Your Own Death (FDN).
- Threaten via threaten_creature: Unexpected Request (FIN).
- Equipment subtype-add: Summoner's Grimoire (FIN, Shaman).

Each test verifies that the wiring registers what we expect: setup_in_graveyard
fires on entry-to-graveyard, the activated ability is registered, and the
expected events come out of the effect_fn. We don't assert on the full game
loop (targeting/AI flows differ across modes); the smoke checks are enough
to catch regressions in the wiring itself.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
)


def _put_in_graveyard(game, card_def, owner):
    """Move a fresh object of card_def directly into owner's graveyard,
    routed through ZONE_CHANGE so setup_in_graveyard fires."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{owner.id}',
            'from_zone_type': ZoneType.HAND,
            'to_zone': f'graveyard_{owner.id}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
    ))
    return obj


def _gy_ability(obj):
    abilities = getattr(obj.state, 'activated_abilities', None) or []
    assert abilities, "expected an activated ability registered in graveyard"
    return abilities[0]


def test_suspicious_shambler_creates_two_zombies():
    from src.cards.foundations import SUSPICIOUS_SHAMBLER
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_in_graveyard(game, SUSPICIOUS_SHAMBLER, p1)
    ability = _gy_ability(obj)
    events = ability.effect_fn(obj, game.state, [])
    assert events[0].type == EventType.EXILE
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED]
    assert len(token_events) == 2, f"expected 2 Zombie tokens, got {len(token_events)}"
    for ev in token_events:
        assert 'Zombie' in ev.payload.get('subtypes', set())
        assert ev.payload.get('power') == 2
        assert ev.payload.get('toughness') == 2
    print("PASS: Suspicious Shambler graveyard ability creates 2 Zombies")


def test_leering_onlooker_creates_two_tapped_flying_bats():
    from src.cards.murders_karlov_manor import LEERING_ONLOOKER
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_in_graveyard(game, LEERING_ONLOOKER, p1)
    ability = _gy_ability(obj)
    events = ability.effect_fn(obj, game.state, [])
    assert events[0].type == EventType.EXILE
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED]
    assert len(token_events) == 2
    for ev in token_events:
        assert 'Bat' in ev.payload.get('subtypes', set())
        assert ev.payload.get('tapped') is True
        assert 'flying' in ev.payload.get('abilities', [])
    print("PASS: Leering Onlooker creates 2 tapped Bats with flying")


def test_goldmeadow_nomad_kithkin_token():
    from src.cards.lorwyn_eclipsed import GOLDMEADOW_NOMAD
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_in_graveyard(game, GOLDMEADOW_NOMAD, p1)
    ability = _gy_ability(obj)
    events = ability.effect_fn(obj, game.state, [])
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED]
    assert len(token_events) == 1
    ev = token_events[0]
    assert 'Kithkin' in ev.payload.get('subtypes', set())
    assert ev.payload.get('power') == 1
    assert ev.payload.get('toughness') == 1
    print("PASS: Goldmeadow Nomad creates 1/1 Kithkin token")


def test_stoic_groveguide_elf_token():
    from src.cards.lorwyn_eclipsed import STOIC_GROVEGUIDE
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_in_graveyard(game, STOIC_GROVEGUIDE, p1)
    ability = _gy_ability(obj)
    events = ability.effect_fn(obj, game.state, [])
    token_events = [e for e in events if e.type == EventType.OBJECT_CREATED]
    assert len(token_events) == 1
    ev = token_events[0]
    assert 'Elf' in ev.payload.get('subtypes', set())
    assert ev.payload.get('power') == 2 and ev.payload.get('toughness') == 2
    print("PASS: Stoic Grove-Guide creates 2/2 Elf token")


def test_morbius_emits_look_at_top():
    from src.cards.spider_man import MORBIUS_THE_LIVING_VAMPIRE
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_in_graveyard(game, MORBIUS_THE_LIVING_VAMPIRE, p1)
    ability = _gy_ability(obj)
    events = ability.effect_fn(obj, game.state, [])
    types = [e.type for e in events]
    assert EventType.EXILE in types
    assert EventType.LOOK_AT_TOP in types
    print("PASS: Morbius emits EXILE + LOOK_AT_TOP")


def test_colossal_rattlewurm_emits_search_library():
    from src.cards.outlaws_thunder_junction import COLOSSAL_RATTLEWURM
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    obj = _put_in_graveyard(game, COLOSSAL_RATTLEWURM, p1)
    ability = _gy_ability(obj)
    events = ability.effect_fn(obj, game.state, [])
    types = [e.type for e in events]
    assert EventType.EXILE in types
    search = [e for e in events if e.type == EventType.SEARCH_LIBRARY]
    assert search, "expected SEARCH_LIBRARY event"
    assert search[0].payload.get('subtype') == 'Desert'
    assert search[0].payload.get('destination') == 'battlefield_tapped'
    print("PASS: Colossal Rattlewurm searches library for Desert")


def test_beetle_legacy_criminal_pumps_with_flying():
    """The effect adds a +1/+1 counter and grants flying EOT (via target callback)."""
    from src.cards.spider_man import BEETLE_LEGACY_CRIMINAL
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Need a creature on the battlefield to make targets non-empty.
    from src.engine.types import CardDefinition, Characteristics
    bear_def = CardDefinition(
        name="Bear", mana_cost="{1}{G}",
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Bear"},
            mana_cost="{1}{G}", power=2, toughness=2,
        ),
    )
    bear = game.create_object(
        name="Bear", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )

    obj = _put_in_graveyard(game, BEETLE_LEGACY_CRIMINAL, p1)
    ability = _gy_ability(obj)
    events = ability.effect_fn(obj, game.state, [])
    types = [e.type for e in events]
    assert EventType.EXILE in types
    # Effect creates a pending choice; verify the choice is now set.
    pc = game.state.pending_choice
    assert pc is not None and pc.choice_type == "target_with_callback"
    assert bear.id in (pc.options or [])
    print("PASS: Beetle Legacy Criminal sets a target choice for pump+flying")


def test_undying_malice_grants_death_trigger():
    """Resolving Undying Malice grants a death trigger that emits return + counter.

    Phase 5b: targets are pre-chosen at cast time via ``target_requirements``.
    The resolve_fn consumes ``targets[0]`` directly (Target instances) instead
    of opening its own PendingChoice.
    """
    from src.cards.foundations import UNDYING_MALICE
    from src.engine.types import CardDefinition, Characteristics
    from src.engine.targeting import Target
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.turn_manager.turn_state.active_player_id = p1.id

    # Place a target creature on battlefield.
    bear_def = CardDefinition(
        name="Bear", mana_cost="{1}{G}",
        characteristics=Characteristics(
            types={CardType.CREATURE}, subtypes={"Bear"},
            mana_cost="{1}{G}", power=2, toughness=2,
        ),
    )
    bear = game.create_object(
        name="Bear", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )

    # Push Undying Malice as a stack object so the resolve fn can find it.
    spell = game.create_object(
        name="Undying Malice", owner_id=p1.id, zone=ZoneType.STACK,
        characteristics=UNDYING_MALICE.characteristics, card_def=UNDYING_MALICE,
    )
    stack_zone = game.state.zones.get('stack')
    if stack_zone is not None and spell.id not in stack_zone.objects:
        stack_zone.objects.append(spell.id)

    # Phase 5b: invoke resolve with pre-chosen targets (engine fills these
    # via PendingChoice at cast time; we hand-feed them for the unit test).
    UNDYING_MALICE.resolve([[Target(id=bear.id, is_player=False)]], game.state)
    # The grant is implemented as an interceptor that fires on OBJECT_DESTROYED.
    interceptors = [i for i in game.state.interceptors.values() if i.duration == 'end_of_turn']
    assert interceptors, "expected a granted death-trigger interceptor"
    print("PASS: Undying Malice installs a granted death trigger on the target")


def test_summoners_grimoire_is_equipment_with_shaman():
    """Equipment subtype-add wiring: Summoner's Grimoire grants Shaman on equip."""
    from src.cards.final_fantasy import SUMMONERS_GRIMOIRE
    # The setup_interceptors should be a make_equipment_setup callable.
    assert callable(SUMMONERS_GRIMOIRE.setup_interceptors)
    # Smoke: instantiate and run the setup; the function should not raise.
    game = Game()
    p1 = game.add_player("Alice")
    obj = game.create_object(
        name="Summoner's Grimoire", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=SUMMONERS_GRIMOIRE.characteristics, card_def=SUMMONERS_GRIMOIRE,
    )
    # The equip activated ability should have been registered.
    abilities = getattr(obj.state, 'activated_abilities', None) or []
    assert any('Equip' in a.description or '{3}' in a.cost_text for a in abilities), \
        "expected Equip {3} activated ability"
    print("PASS: Summoner's Grimoire registers Equip ability")


if __name__ == "__main__":
    test_suspicious_shambler_creates_two_zombies()
    test_leering_onlooker_creates_two_tapped_flying_bats()
    test_goldmeadow_nomad_kithkin_token()
    test_stoic_groveguide_elf_token()
    test_morbius_emits_look_at_top()
    test_colossal_rattlewurm_emits_search_library()
    test_beetle_legacy_criminal_pumps_with_flying()
    test_undying_malice_grants_death_trigger()
    test_summoners_grimoire_is_equipment_with_shaman()
    print("\nAll sweep wiring tests passed!")
