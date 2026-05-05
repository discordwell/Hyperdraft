"""
Test Ward Mechanic

Tests for the Ward static ability and its underlying TARGET_CHOSEN event:
- TARGET_CHOSEN fires when a spell's targets are committed to a stack item.
- Ward fires on opponent's targeted spell (counters it).
- Ward does NOT fire on owner's own spell.
- Ward fires once per opponent-targeted spell (multiple in one turn).
- Ward via Equipment is granted to the equipped creature, not the equipment.

Note: per ward_replacement v1, Ward emits COUNTER_SPELL_UNLESS_PAY which the
existing system interceptor in game.py treats as an unconditional counter (no
cost-payment prompt yet). Tests assert the spell is countered.
"""

import os
import sys
# Resolve project root from this test file. Avoids picking up a stale clone in
# /Users/discordwell/Projects/Hyperdraft/ that other tests hard-code.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    PendingChoice, Interceptor,
)
from src.engine.types import Characteristics, CardDefinition, new_id
from src.engine.targeting import Target
from src.engine.stack import (
    StackItem, StackItemType, TriggeredStackItem,
    build_target_chosen_events,
    process_pending_triggers,
)
from src.cards.interceptor_helpers import (
    make_ward,
    make_equipment_setup,
    make_aura_setup,
)


# =============================================================================
# Helpers
# =============================================================================

def create_test_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def make_creature_obj(game, owner, name, power, toughness, *, setup_fn=None,
                     subtypes=None, types=None):
    """Put a creature on the battlefield. Returns the GameObject."""
    characteristics = Characteristics(
        types=set(types) if types else {CardType.CREATURE},
        subtypes=set(subtypes) if subtypes else set(),
        power=power,
        toughness=toughness,
    )
    card_def = CardDefinition(
        name=name, mana_cost="{1}",
        characteristics=characteristics,
        setup_interceptors=setup_fn,
    )
    obj = game.create_object(
        name=name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=characteristics, card_def=card_def,
    )
    # Move to battlefield via the pipeline so setup_interceptors fire.
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{owner.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def make_artifact_obj(game, owner, name, *, setup_fn=None, subtypes=None):
    """Put an artifact on the battlefield. Returns the GameObject."""
    characteristics = Characteristics(
        types={CardType.ARTIFACT},
        subtypes=set(subtypes) if subtypes else set(),
    )
    card_def = CardDefinition(
        name=name, mana_cost="{1}",
        characteristics=characteristics,
        setup_interceptors=setup_fn,
    )
    obj = game.create_object(
        name=name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=characteristics, card_def=card_def,
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{owner.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def push_targeted_spell(game, caster, target_id, *, name="Test Bolt"):
    """Synthesise a spell on the stack targeting ``target_id``, then emit the
    TARGET_CHOSEN events the priority cast handler would fire.

    Returns the StackItem (still on the stack until countered or resolved).
    """
    spell_chars = Characteristics(types={CardType.INSTANT})
    spell_def = CardDefinition(
        name=name, mana_cost="{1}{R}",
        characteristics=spell_chars,
        text=f"Deal 3 damage to target.",
    )
    spell_obj = game.create_object(
        name=name, owner_id=caster.id, zone=ZoneType.HAND,
        characteristics=spell_chars, card_def=spell_def,
    )

    item = StackItem(
        id=new_id(),
        type=StackItemType.SPELL,
        source_id=spell_obj.id,
        controller_id=caster.id,
        card_id=spell_obj.id,
        chosen_targets=[[Target(id=target_id, is_player=False)]],
    )
    game.stack.push(item)

    # Now emit TARGET_CHOSEN events as the priority cast handler would.
    target_events = build_target_chosen_events(
        spell_id=spell_obj.id,
        controller_id=caster.id,
        targets=[[Target(id=target_id, is_player=False)]],
    )
    for ev in target_events:
        game.emit(ev)

    return item, spell_obj


# =============================================================================
# build_target_chosen_events
# =============================================================================

def test_build_target_chosen_events_one_target():
    """build_target_chosen_events emits one event per chosen target."""
    print("\n=== Test: build_target_chosen_events ===")
    targets = [[Target(id="creature_1", is_player=False)]]
    events = build_target_chosen_events(
        spell_id="spell_1", controller_id="player_1", targets=targets,
    )
    assert len(events) == 1
    assert events[0].type == EventType.TARGET_CHOSEN
    assert events[0].payload['spell_id'] == "spell_1"
    assert events[0].payload['target_id'] == "creature_1"
    assert events[0].payload['controller'] == "player_1"
    print("  one target -> one event")


def test_build_target_chosen_events_multiple_targets():
    """Two requirements with one target each yields two TARGET_CHOSEN events."""
    targets = [
        [Target(id="t1", is_player=False)],
        [Target(id="t2", is_player=False)],
    ]
    events = build_target_chosen_events(
        spell_id="spell_a", controller_id="p1", targets=targets,
    )
    assert len(events) == 2
    assert events[0].payload['target_id'] == "t1"
    assert events[1].payload['target_id'] == "t2"


def test_build_target_chosen_events_no_targets():
    """No targets -> no events (untargeted spells don't fire TARGET_CHOSEN)."""
    assert build_target_chosen_events("spell_a", "p1", None) == []
    assert build_target_chosen_events("spell_a", "p1", []) == []
    assert build_target_chosen_events("spell_a", "p1", [[]]) == []


def test_build_target_chosen_events_string_ids():
    """Plain string IDs (legacy callers) still produce events."""
    events = build_target_chosen_events("spell_a", "p1", [["t1", "t2"]])
    assert len(events) == 2
    assert events[0].payload['target_id'] == "t1"
    assert events[1].payload['target_id'] == "t2"


# =============================================================================
# make_ward direct tests
# =============================================================================

def test_make_ward_counters_opponent_spell():
    """A warded creature counters an opponent's targeted spell."""
    print("\n=== Test: Ward counters opponent's spell ===")
    game, p1, p2 = create_test_game()

    # P1 controls a Ward {1} creature.
    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Warded Beast", 3, 3, setup_fn=setup_fn)

    # P2 (opponent) casts a spell at the warded creature.
    item, spell_obj = push_targeted_spell(game, p2, warded.id, name="Opp's Bolt")

    # Ward should have countered the spell. The stack should no longer contain
    # the spell (counter handler in game.py pops stack items via state.stack).
    assert game.stack.size() == 0, (
        f"Expected stack empty after ward, got {game.stack.size()} items"
    )
    # Spell card should have moved out of STACK zone (countered → graveyard).
    assert spell_obj.zone != ZoneType.STACK, (
        f"Expected countered spell to leave stack, found {spell_obj.zone}"
    )
    print("  ward fired and countered opponent's spell")


def test_make_ward_does_not_fire_on_own_spell():
    """A warded creature does NOT trigger Ward when its own controller targets it."""
    print("\n=== Test: Ward does not fire on own spell ===")
    game, p1, p2 = create_test_game()

    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Self-Warded", 2, 2, setup_fn=setup_fn)

    # P1 (the warded creature's owner) targets it. Ward should NOT fire.
    item, spell_obj = push_targeted_spell(game, p1, warded.id, name="P1's Pump")

    assert game.stack.size() == 1, (
        f"Expected spell still on stack (no ward fire), got {game.stack.size()}"
    )
    assert spell_obj.zone == ZoneType.STACK, (
        f"Expected own spell still on stack, found {spell_obj.zone}"
    )
    print("  own spell unaffected")


def test_make_ward_does_not_fire_self_targeting():
    """Ward does not fire when source == self (e.g. own ability targeting self).

    This is the "ability source = self" case from the spec. We simulate it by
    casting from the warded creature's own controller on the warded creature
    itself (most common path: a creature's own activated ability targeting it,
    e.g. equip activations are exempt because they originate from the same
    controller).
    """
    print("\n=== Test: Ward does not fire when source is self-controlled ===")
    game, p1, _ = create_test_game()

    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{2}{U}")]
    warded = make_creature_obj(game, p1, "Self-Bouncer", 2, 2, setup_fn=setup_fn)

    # Same controller targets self with a synthetic ability event.
    game.emit(Event(
        type=EventType.TARGET_CHOSEN,
        payload={
            'spell_id': warded.id,  # self-source
            'target_id': warded.id,
            'controller': p1.id,
        },
        source=warded.id,
        controller=p1.id,
    ))

    # No COUNTER_SPELL_UNLESS_PAY should have been generated (no stack item to
    # pop, but more importantly, the Ward filter should reject the event).
    counter_events = [
        e for e in game.state.event_log
        if e.type == EventType.COUNTER_SPELL_UNLESS_PAY
    ]
    assert not counter_events, (
        f"Expected ward to NOT fire, got {len(counter_events)} counter events"
    )
    print("  ward filtered out same-controller TARGET_CHOSEN")


def test_make_ward_fires_each_opponent_spell():
    """Ward fires for every opponent-targeted spell, not just the first."""
    print("\n=== Test: Ward fires for each opponent spell ===")
    game, p1, p2 = create_test_game()

    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Constantly Warded", 4, 4, setup_fn=setup_fn)

    # Three sequential opponent spells targeting the warded creature.
    counter_count = 0
    for i in range(3):
        item, spell_obj = push_targeted_spell(
            game, p2, warded.id, name=f"Opp Spell #{i+1}",
        )
        # Each one should be countered immediately.
        assert spell_obj.zone != ZoneType.STACK, (
            f"Spell {i+1} should have been countered"
        )
        counter_count += 1

    assert counter_count == 3
    # Verify three COUNTER_SPELL_UNLESS_PAY events were emitted.
    counters = [
        e for e in game.state.event_log
        if e.type == EventType.COUNTER_SPELL_UNLESS_PAY
        and e.payload.get('reason') == 'ward'
    ]
    assert len(counters) == 3, (
        f"Expected 3 ward COUNTER_SPELL_UNLESS_PAY events, got {len(counters)}"
    )
    print(f"  three opponent spells -> three ward counters")


# =============================================================================
# Equipment / Aura ward integration
# =============================================================================

def test_equipment_grants_ward_to_equipped():
    """make_equipment_setup(ward_cost=...) grants Ward to the equipped creature."""
    print("\n=== Test: Equipment grants ward to equipped creature ===")
    game, p1, p2 = create_test_game()

    boots_setup = make_equipment_setup(
        power_mod=1, toughness_mod=0, keywords=["haste"],
        equip_cost="{1}", ward_cost="{1}",
    )
    boots = make_artifact_obj(
        game, p1, "Lavaspur-like Boots",
        setup_fn=boots_setup, subtypes={"Equipment"},
    )
    creature = make_creature_obj(game, p1, "Equipped Hero", 2, 2)

    # Attach boots → creature.
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': boots.id, 'target_id': creature.id},
        source=boots.id, controller=p1.id,
    ))
    assert creature.id == boots.state.attached_to

    # Opponent targets the equipped creature.
    item, spell_obj = push_targeted_spell(game, p2, creature.id, name="Opp's Removal")
    assert game.stack.size() == 0, (
        "Equipment-granted ward should have countered opponent's spell"
    )
    print("  equipped creature gained ward, opponent spell countered")


def test_equipment_ward_does_not_protect_self():
    """Equipment's ward does not fire on the equipment itself, only the
    equipped creature."""
    print("\n=== Test: Equipment ward only protects equipped creature ===")
    game, p1, p2 = create_test_game()

    boots_setup = make_equipment_setup(
        power_mod=1, toughness_mod=0, ward_cost="{1}",
    )
    boots = make_artifact_obj(
        game, p1, "Test Boots",
        setup_fn=boots_setup, subtypes={"Equipment"},
    )
    creature = make_creature_obj(game, p1, "Carrier", 2, 2)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': boots.id, 'target_id': creature.id},
        source=boots.id, controller=p1.id,
    ))

    # Opponent targets the BOOTS, not the equipped creature.
    item, spell_obj = push_targeted_spell(game, p2, boots.id, name="Shatter")
    # Spell should still be on the stack (no ward on boots itself).
    assert game.stack.size() == 1, (
        f"Expected spell still on stack (boots shouldn't ward themselves), "
        f"got {game.stack.size()}"
    )
    print("  equipment is not warded; only the equipped creature is")


def test_aura_grants_ward_to_enchanted():
    """make_aura_setup(ward_cost=...) grants Ward to the enchanted creature."""
    print("\n=== Test: Aura grants ward to enchanted creature ===")
    game, p1, p2 = create_test_game()

    creature = make_creature_obj(game, p1, "Aura Carrier", 2, 2)

    # Build an Aura that will attach to the creature on ETB.
    def aura_setup(obj, state):
        # Pre-set the target so make_aura_setup picks it up.
        setattr(obj.state, "_aura_target_id", creature.id)
        inner = make_aura_setup(
            power_mod=1, toughness_mod=0, keywords=["lifelink"],
            ward_cost="{2}",
        )
        return inner(obj, state)

    aura_chars = Characteristics(
        types={CardType.ENCHANTMENT}, subtypes={"Aura"},
    )
    aura_def = CardDefinition(
        name="Test Aura", mana_cost="{1}{W}",
        characteristics=aura_chars,
        setup_interceptors=aura_setup,
    )
    aura = game.create_object(
        name="Test Aura", owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=aura_chars, card_def=aura_def,
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': aura.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    # Aura setup should have linked attached_to.
    assert aura.state.attached_to == creature.id, (
        f"Expected aura attached to creature {creature.id}, got "
        f"{aura.state.attached_to}"
    )

    # Opponent targets the enchanted creature.
    item, spell_obj = push_targeted_spell(game, p2, creature.id, name="Opp Removal")
    assert game.stack.size() == 0, (
        "Aura-granted ward should have countered opponent's spell"
    )
    print("  enchanted creature gained ward, opponent spell countered")


# =============================================================================
# Card-level wiring smoke tests
# =============================================================================

def test_armored_armadillo_grants_ward():
    """ARMORED_ARMADILLO from outlaws_thunder_junction wires ward {1}."""
    print("\n=== Test: ARMORED_ARMADILLO has ward {1} ===")
    from src.cards.outlaws_thunder_junction import ARMORED_ARMADILLO
    import copy
    game, p1, p2 = create_test_game()

    # Recreate the card on the battlefield via the standard create_object path.
    armadillo = game.create_object(
        name=ARMORED_ARMADILLO.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=copy.deepcopy(ARMORED_ARMADILLO.characteristics),
        card_def=ARMORED_ARMADILLO,
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': armadillo.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))

    # Opponent targets the armadillo.
    item, spell_obj = push_targeted_spell(game, p2, armadillo.id, name="Opp Removal")
    assert game.stack.size() == 0, "Armored Armadillo should be ward-protected"
    print("  ARMORED_ARMADILLO wired ward {1}")


def test_lavaspur_boots_grants_ward_to_equipped():
    """LAVASPUR_BOOTS grants ward {1} to its equipped creature."""
    print("\n=== Test: LAVASPUR_BOOTS grants ward to equipped ===")
    from src.cards.outlaws_thunder_junction import LAVASPUR_BOOTS
    import copy
    game, p1, p2 = create_test_game()

    boots = game.create_object(
        name=LAVASPUR_BOOTS.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=copy.deepcopy(LAVASPUR_BOOTS.characteristics),
        card_def=LAVASPUR_BOOTS,
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': boots.id, 'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield', 'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    creature = make_creature_obj(game, p1, "Wearer", 2, 2)
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': boots.id, 'target_id': creature.id},
        source=boots.id, controller=p1.id,
    ))

    item, spell_obj = push_targeted_spell(game, p2, creature.id, name="Opp Bolt")
    assert game.stack.size() == 0, (
        "Equipped creature should be ward-protected by Lavaspur Boots"
    )
    print("  LAVASPUR_BOOTS grants ward {1} to equipped")


def _assert_card_wires_ward(card_def, label):
    """Helper: place ``card_def`` on the battlefield, verify opponent's
    targeted spell is countered by ward."""
    import copy
    game, p1, p2 = create_test_game()
    obj = game.create_object(
        name=card_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=copy.deepcopy(card_def.characteristics),
        card_def=card_def,
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{p1.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    item, spell_obj = push_targeted_spell(game, p2, obj.id, name="Opp Removal")
    assert game.stack.size() == 0, (
        f"{label} should ward-counter opponent's spell; stack still has "
        f"{game.stack.size()} items"
    )


def test_noop_ward_cards_wired():
    """All previously-noop ward cards now wire ward via setup_interceptors.
    Covers Toadstool Admirer, Roaming Throne, Tolarian Terror, Spider-Rex,
    Fblthp, Spinewoods Armadillo, and the MKM disguise placeholder set.
    """
    print("\n=== Test: previously noop ward cards now wire ward ===")
    from src.cards.wilds_of_eldraine import TOADSTOOL_ADMIRER
    from src.cards.lost_caverns_ixalan import ROAMING_THRONE
    from src.cards.murders_karlov_manor import (
        DEFENESTRATED_PHANTOM, ESSENCE_OF_ANTIQUITY, MISTWAY_SPY,
        BOLRACCLAN_BASHER, FUGITIVE_CODEBREAKER, PYROTECHNIC_PERFORMER,
        NERVOUS_GARDENER, DOG_WALKER, FAERIE_SNOOP, RIFTBURST_HELLION,
        LUMBERING_LAUNDRY, BRANCH_OF_VITUGHAZI,
    )
    from src.cards.outlaws_thunder_junction import (
        FBLTHP_LOST_ON_THE_RANGE, SPINEWOODS_ARMADILLO,
    )
    from src.cards.foundations import TOLARIAN_TERROR
    from src.cards.spider_man import SPIDERREX_DARING_DINO

    # Each entry: (card_def, label). All use ward {2} except SPINEWOODS ({3}).
    candidates = [
        (TOADSTOOL_ADMIRER, "Toadstool Admirer"),
        (ROAMING_THRONE, "Roaming Throne"),
        (DEFENESTRATED_PHANTOM, "Defenestrated Phantom"),
        (ESSENCE_OF_ANTIQUITY, "Essence of Antiquity"),
        (MISTWAY_SPY, "Mistway Spy"),
        (BOLRACCLAN_BASHER, "Bolrac-Clan Basher"),
        (FUGITIVE_CODEBREAKER, "Fugitive Codebreaker"),
        (PYROTECHNIC_PERFORMER, "Pyrotechnic Performer"),
        (NERVOUS_GARDENER, "Nervous Gardener"),
        (DOG_WALKER, "Dog Walker"),
        (FAERIE_SNOOP, "Faerie Snoop"),
        (RIFTBURST_HELLION, "Riftburst Hellion"),
        (LUMBERING_LAUNDRY, "Lumbering Laundry"),
        (BRANCH_OF_VITUGHAZI, "Branch of Vitu-Ghazi"),
        (FBLTHP_LOST_ON_THE_RANGE, "Fblthp, Lost on the Range"),
        (SPINEWOODS_ARMADILLO, "Spinewoods Armadillo"),
        (TOLARIAN_TERROR, "Tolarian Terror"),
        (SPIDERREX_DARING_DINO, "Spider-Rex, Daring Dino"),
    ]
    for card_def, label in candidates:
        _assert_card_wires_ward(card_def, label)
    print(f"  {len(candidates)} previously-noop ward cards now ward-protected")


# =============================================================================
# Test runner
# =============================================================================

# =============================================================================
# TriggeredStackItem framework integration (W22)
# =============================================================================

def test_ward_marked_as_triggered_ability():
    """make_ward returns an interceptor with is_triggered_ability=True."""
    print("\n=== Test: Ward interceptor is marked as triggered ability ===")
    game, p1, _p2 = create_test_game()

    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Marked", 2, 2, setup_fn=setup_fn)

    # Find the ward interceptor on the warded creature.
    ward_ints = [
        game.state.interceptors[i_id]
        for i_id in warded.interceptor_ids
        if i_id in game.state.interceptors
    ]
    assert ward_ints, "Expected at least one ward interceptor on warded"
    # All registered interceptors here should be ward triggers.
    for w in ward_ints:
        assert getattr(w, 'is_triggered_ability', False), (
            "make_ward must set is_triggered_ability=True"
        )
        assert getattr(w, 'effect_fn', None) is not None, (
            "make_ward must store effect_fn for the trigger framework"
        )
    print("  Ward interceptor carries is_triggered_ability + effect_fn")


def test_ward_queues_when_auto_resolve_disabled():
    """With auto_resolve_triggers=False, Ward enqueues a TriggeredStackItem
    instead of firing inline."""
    print("\n=== Test: Ward queues TriggeredStackItem (no auto-resolve) ===")
    game, p1, p2 = create_test_game()
    game.state.options.auto_resolve_triggers = False

    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Queued Beast", 3, 3, setup_fn=setup_fn)

    # Opponent casts a spell at the warded creature.
    item, spell_obj = push_targeted_spell(game, p2, warded.id, name="Opp Bolt")

    # Without auto-resolve, the spell should still be on the stack — Ward
    # should be queued in pending_triggers, not fired.
    assert game.stack.size() == 1, (
        f"Expected spell still on stack while ward is queued, got "
        f"{game.stack.size()} items"
    )
    assert spell_obj.zone == ZoneType.STACK, (
        f"Spell should still be on the stack pre-drain, got {spell_obj.zone}"
    )
    # Ward trigger should be in pending_triggers.
    assert len(game.state.pending_triggers) == 1, (
        f"Expected 1 ward trigger queued, got {len(game.state.pending_triggers)}"
    )
    trig = game.state.pending_triggers[0]
    assert isinstance(trig, TriggeredStackItem)
    assert trig.controller == p1.id, (
        f"Ward trigger controller should be the warded creature's controller "
        f"(p1={p1.id}); got {trig.controller}"
    )
    assert trig.source_id == warded.id
    print("  Ward queued instead of firing inline")


def test_ward_resolves_before_spell_via_drain():
    """With auto-resolve disabled, draining the queue puts Ward on top of
    the stack so it resolves before the warded spell (CR 603 priority)."""
    print("\n=== Test: Ward resolves before spell after drain ===")
    game, p1, p2 = create_test_game()
    game.state.options.auto_resolve_triggers = False

    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Stacked Beast", 3, 3, setup_fn=setup_fn)

    # Opponent casts a spell at the warded creature.
    item, spell_obj = push_targeted_spell(game, p2, warded.id, name="Opp Bolt")

    # Pre-drain: spell on stack, Ward queued.
    assert game.stack.size() == 1
    assert len(game.state.pending_triggers) == 1

    # Drain the queue. Ward gets pushed onto the stack on top of the spell.
    pushed = process_pending_triggers(game.state, game.stack)
    assert pushed == 1, f"Expected 1 ward trigger pushed, got {pushed}"
    assert game.stack.size() == 2, (
        f"Expected stack to hold spell+ward, got {game.stack.size()} items"
    )
    # Top of stack should be the Ward TriggeredStackItem (resolves first).
    top = game.stack.top()
    assert isinstance(top, TriggeredStackItem), (
        f"Top of stack should be a TriggeredStackItem, got {type(top).__name__}"
    )
    assert top.source_id == warded.id

    # Resolve the top item — Ward fires, emits COUNTER_SPELL_UNLESS_PAY.
    events = game.stack.resolve_top()
    assert events, "Ward resolution should produce events"
    counter_events = [e for e in events if e.type == EventType.COUNTER_SPELL_UNLESS_PAY]
    assert len(counter_events) == 1, (
        f"Expected 1 COUNTER_SPELL_UNLESS_PAY event from Ward, got "
        f"{len(counter_events)}"
    )
    # Now emit those events through the pipeline so the system counterspell
    # glue can handle them.
    for ev in events:
        game.emit(ev)

    # Spell should now be countered → out of stack.
    assert game.stack.is_empty(), (
        f"Stack should be empty after Ward counters spell, got "
        f"{game.stack.size()} items: {[type(x).__name__ for x in game.stack.items]}"
    )
    assert spell_obj.zone != ZoneType.STACK, (
        f"Countered spell should leave stack, got {spell_obj.zone}"
    )
    print("  Ward resolved on top of stack, countered the warded spell")


def test_ward_multiple_targets_apnap_ordering():
    """A spell with two targets — both warded by different opponent creatures
    — fires two Ward triggers that drain in APNAP order."""
    print("\n=== Test: Ward APNAP with multiple targets ===")
    game, p1, p2 = create_test_game()
    game.state.options.auto_resolve_triggers = False
    # Active player is p2 (the spell's caster). Triggers controlled by p1
    # (NAP) come second; only p1 has ward triggers, so APNAP ordering still
    # produces a deterministic batch.
    game.turn_manager.turn_state.active_player_id = p2.id

    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    a = make_creature_obj(game, p1, "Warded A", 2, 2, setup_fn=setup_fn)
    b = make_creature_obj(game, p1, "Warded B", 2, 2, setup_fn=setup_fn)

    # Build a multi-target spell from p2 hitting both A and B.
    spell_chars = Characteristics(types={CardType.INSTANT})
    spell_def = CardDefinition(
        name="Forked Bolt", mana_cost="{1}{R}",
        characteristics=spell_chars,
        text="Two targets.",
    )
    spell_obj = game.create_object(
        name="Forked Bolt", owner_id=p2.id, zone=ZoneType.HAND,
        characteristics=spell_chars, card_def=spell_def,
    )
    item = StackItem(
        id=new_id(),
        type=StackItemType.SPELL,
        source_id=spell_obj.id,
        controller_id=p2.id,
        card_id=spell_obj.id,
        chosen_targets=[[Target(id=a.id, is_player=False),
                         Target(id=b.id, is_player=False)]],
    )
    game.stack.push(item)
    target_events = build_target_chosen_events(
        spell_id=spell_obj.id,
        controller_id=p2.id,
        targets=[[Target(id=a.id, is_player=False),
                  Target(id=b.id, is_player=False)]],
    )
    for ev in target_events:
        game.emit(ev)

    # Two Ward triggers should be queued (one per warded target).
    assert len(game.state.pending_triggers) == 2, (
        f"Expected 2 ward triggers, got {len(game.state.pending_triggers)}"
    )
    for t in game.state.pending_triggers:
        assert isinstance(t, TriggeredStackItem)
        assert t.controller == p1.id, (
            f"Both ward triggers should be controlled by p1, got {t.controller}"
        )

    # Drain. With p2 active, p1 is NAP — both triggers belong to NAP and
    # are pushed last (so they're on top, LIFO resolves them first). Stack
    # holds [spell, ward_a, ward_b] (order within bucket is registration).
    pushed = process_pending_triggers(game.state, game.stack)
    assert pushed == 2
    assert game.stack.size() == 3
    # Top item is one of the Ward triggers.
    items = game.stack.get_items()
    assert isinstance(items[1], TriggeredStackItem)
    assert isinstance(items[2], TriggeredStackItem)
    # The bottom item is the original spell.
    assert items[0].id == item.id, (
        "Original spell should still be at the bottom of the stack"
    )

    # Resolve top: first Ward fires, counters the spell.
    events1 = game.stack.resolve_top()
    for ev in events1:
        game.emit(ev)
    # The spell was countered by the first Ward firing — once that's done,
    # the second Ward trigger remains on the stack but its target spell is
    # gone from the stack. We resolve it; the COUNTER_SPELL_UNLESS_PAY for
    # an already-gone spell is a no-op (system glue finds no matching item).
    if not game.stack.is_empty():
        events2 = game.stack.resolve_top()
        for ev in events2:
            game.emit(ev)
    # Original spell countered; stack ultimately empty.
    assert game.stack.is_empty(), (
        f"Expected empty stack after both ward triggers drained, got "
        f"{game.stack.size()} items"
    )
    assert spell_obj.zone != ZoneType.STACK
    print("  Two ward triggers drained APNAP, spell countered")


def test_ward_marker_event_emitted_when_queued():
    """When Ward queues, a TRIGGERED_ABILITY_PUT_ON_STACK marker fires (via
    the auto-resolve drain in the pipeline)."""
    print("\n=== Test: Ward emits TRIGGERED_ABILITY_PUT_ON_STACK marker ===")
    game, p1, p2 = create_test_game()
    # Auto-resolve True so the pipeline drain emits the marker.
    def setup_fn(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Marker Beast", 3, 3, setup_fn=setup_fn)

    pre_log_size = len(game.state.event_log)
    item, spell_obj = push_targeted_spell(game, p2, warded.id, name="Opp Bolt")

    markers = [
        e for e in game.state.event_log[pre_log_size:]
        if e.type == EventType.TRIGGERED_ABILITY_PUT_ON_STACK
        and e.payload.get('source_id') == warded.id
    ]
    assert markers, (
        f"Expected at least one TRIGGERED_ABILITY_PUT_ON_STACK marker for "
        f"the ward trigger; got {len(markers)}"
    )
    print(f"  marker emitted (description={markers[0].payload.get('description')!r})")


def test_ward_handler_fallback_when_flag_disabled():
    """If a caller flips is_triggered_ability=False (e.g. legacy tests),
    the handler still emits COUNTER_SPELL_UNLESS_PAY directly. This is the
    fallback path through Interceptor.handler."""
    print("\n=== Test: Ward handler-fallback path ===")
    from src.engine.types import InterceptorAction
    game, p1, p2 = create_test_game()

    # Build the ward interceptor manually so we can inspect/flip flags.
    def setup_fn(obj, state):
        ward = make_ward(obj, mana_cost="{1}")
        # Force the legacy inline-handler path.
        ward.is_triggered_ability = False
        return [ward]
    warded = make_creature_obj(game, p1, "Legacy Ward", 2, 2, setup_fn=setup_fn)

    item, spell_obj = push_targeted_spell(game, p2, warded.id, name="Opp Bolt")
    # Even without is_triggered_ability, the handler returns a REACT result
    # and the system glue counters the spell.
    assert game.stack.is_empty(), (
        f"Even with is_triggered_ability=False the legacy handler should "
        f"counter the spell, got {game.stack.size()}"
    )
    assert spell_obj.zone != ZoneType.STACK
    print("  legacy fallback path still counters the spell")


def test_make_ward_fires_on_activated_ability_target():
    """Ward fires on activated-ability targeting too (not just spells)."""
    print("\n=== Test: Ward fires on activated-ability target ===")
    import asyncio
    from src.engine.priority import ActionType, PlayerAction
    from src.engine.turn import Phase
    from src.cards.interceptor_helpers import make_activated_ability

    game, p1, p2 = create_test_game()

    # P1 controls a Ward {1} creature.
    def warded_setup(obj, state):
        return [make_ward(obj, mana_cost="{1}")]
    warded = make_creature_obj(game, p1, "Warded Beast", 3, 3, setup_fn=warded_setup)

    # P2 controls a creature with a {T}: damage-target activated ability.
    def attacker_setup(obj, state):
        def effect(o, st, targets):
            if not targets:
                return []
            t = targets[0]
            tid = getattr(t, "id", None) or t
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': tid, 'amount': 1, 'source': o.id},
                source=o.id, controller=o.controller,
            )]
        make_activated_ability(
            obj, "{T}", effect,
            description="Deal 1 damage to any target",
            targets_required=1, target_kind="any",
        )
        return []
    attacker = make_creature_obj(game, p2, "Sniper", 1, 1, setup_fn=attacker_setup)
    attacker.state.summoning_sickness = False
    game.turn_manager.turn_state.active_player_id = p2.id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

    # P2 activates the ability targeting the warded creature.
    action = PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=p2.id, source_id=attacker.id,
        ability_id="activated:0",
        targets=[[Target(id=warded.id)]],
    )
    events = asyncio.get_event_loop().run_until_complete(
        game.priority_system._handle_activate_ability(action),
    )

    target_chosen = [e for e in events if e.type == EventType.TARGET_CHOSEN]
    assert target_chosen, "expected TARGET_CHOSEN events from activated ability"
    # The TARGET_CHOSEN event should fire ward → counter the ability.
    for e in events:
        game.emit(e)
    # Stack should now be empty (ability countered).
    assert game.stack.size() == 0, (
        f"expected ward to counter activated ability, stack size = {game.stack.size()}"
    )
    print("  ward fired on activated-ability target")


if __name__ == "__main__":
    tests = [
        test_build_target_chosen_events_one_target,
        test_build_target_chosen_events_multiple_targets,
        test_build_target_chosen_events_no_targets,
        test_build_target_chosen_events_string_ids,
        test_make_ward_counters_opponent_spell,
        test_make_ward_does_not_fire_on_own_spell,
        test_make_ward_does_not_fire_self_targeting,
        test_make_ward_fires_each_opponent_spell,
        test_equipment_grants_ward_to_equipped,
        test_equipment_ward_does_not_protect_self,
        test_aura_grants_ward_to_enchanted,
        test_armored_armadillo_grants_ward,
        test_lavaspur_boots_grants_ward_to_equipped,
        test_noop_ward_cards_wired,
        # W22 — TriggeredStackItem framework integration
        test_ward_marked_as_triggered_ability,
        test_ward_queues_when_auto_resolve_disabled,
        test_ward_resolves_before_spell_via_drain,
        test_ward_multiple_targets_apnap_ordering,
        test_ward_marker_event_emitted_when_queued,
        test_ward_handler_fallback_when_flag_disabled,
        test_make_ward_fires_on_activated_ability_target,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
            import traceback; traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
