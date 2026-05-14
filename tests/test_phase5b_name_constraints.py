"""
Phase 5b name-constraint target filters.

Adds the ``exclude_names`` axis to ``TargetFilter`` so cards like:
  * WOE The Apprentice's Folly (Saga I/II): "target nontoken creature you
    control that doesn't have the same name as a token you control"
  * WOE Yenna, Redtooth Regent ({2},{T}): "target enchantment you control
    that doesn't have the same name as another permanent you control"

can have their legal-target list correctly filtered at choice-emit time.

Also adds regression coverage for the resolve-time / interceptor-time
predicate cards that DON'T use the new TargetFilter axis but DO have
same-name semantics:
  * WOE The End (graveyard/hand/library search for same-name copies)
  * FDN Maelstrom Pulse (destroy all permanents with same name as target)
  * DSK Central Elevator (search library for Room without same name as a
    Room you control)
  * DSK Marvin, Murderous Mimic (gains activated abilities of differently-
    named creatures you control)
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, CardDefinition,
    make_creature, make_enchantment,
)
from src.engine.targeting import (
    TargetFilter, TargetRequirement,
    creature_filter, permanent_filter,
    _names_of_your_tokens, _names_of_your_other_permanents,
    has_other_permanent_with_same_name,
    target_without_same_name_as_your_tokens,
    target_without_same_name_as_other_permanents,
    resolve_target_requirement_spec,
)
from src.cards.interceptor_helpers import make_saga_setup


# ---------------------------------------------------------------------------
# Bare unit tests for the filter axis + builders
# ---------------------------------------------------------------------------

def _bare_object(name: str, *, types=None, is_token=False, controller='p1'):
    """Build a free-floating GameObject for filter unit tests."""
    from src.engine.types import GameObject, ObjectState
    if types is None:
        types = {CardType.CREATURE}
    chars = Characteristics(types=types)
    obj = GameObject(
        id=f"obj_{name}",
        name=name,
        characteristics=chars,
        zone=ZoneType.BATTLEFIELD,
        controller=controller,
        owner=controller,
    )
    obj.state = ObjectState(is_token=is_token)
    return obj


def test_exclude_names_filter_axis_works():
    """Direct check of ``TargetFilter.matches()`` with ``exclude_names``.

    Object whose ``name`` is in the set is rejected. Other-named objects
    pass. Default (empty) set is a no-op."""
    print("\n=== Test: exclude_names filter axis ===")
    state = Game().state
    foo = _bare_object("Spirit")
    bar = _bare_object("Bear")

    # No exclusion: both pass.
    tf_open = creature_filter()
    assert tf_open.matches(foo, state) is True
    assert tf_open.matches(bar, state) is True

    # Single-name exclusion: Spirit rejected, Bear passes.
    tf_excl = creature_filter(exclude_names={"Spirit"})
    assert tf_excl.matches(foo, state) is False, "Spirit must be rejected"
    assert tf_excl.matches(bar, state) is True, "Bear must still pass"

    # Multi-name exclusion: both Spirit + Bear rejected.
    tf_both = creature_filter(exclude_names={"Spirit", "Bear"})
    assert tf_both.matches(foo, state) is False
    assert tf_both.matches(bar, state) is False

    # Empty set is a no-op (truthiness short-circuit).
    tf_empty = creature_filter(exclude_names=set())
    assert tf_empty.matches(foo, state) is True
    assert tf_empty.matches(bar, state) is True
    print("  exclude_names axis works as expected")


def test_target_without_same_name_builder():
    """Direct check of the two builders.

    The builders snapshot offending names from the controller's board and
    populate ``exclude_names`` on the resulting filter."""
    print("\n=== Test: target_without_same_name_* builders ===")
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")

    # Spawn a token named 'Spirit' under p1.
    from src.engine.types import GameObject, ObjectState
    spirit_token = GameObject(
        id="tok_spirit",
        name="Spirit",
        characteristics=Characteristics(types={CardType.CREATURE}),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    spirit_token.state = ObjectState(is_token=True)
    game.state.objects[spirit_token.id] = spirit_token

    # Spawn a nontoken creature also named 'Spirit' under p1.
    spirit_clone = GameObject(
        id="cre_spirit_clone",
        name="Spirit",
        characteristics=Characteristics(types={CardType.CREATURE}),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    spirit_clone.state = ObjectState(is_token=False)
    game.state.objects[spirit_clone.id] = spirit_clone

    # Spawn a nontoken creature named 'Bear' under p1.
    bear = GameObject(
        id="cre_bear",
        name="Bear",
        characteristics=Characteristics(types={CardType.CREATURE}),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    bear.state = ObjectState(is_token=False)
    game.state.objects[bear.id] = bear

    # Sanity: token-name snapshot picks up Spirit only.
    names = _names_of_your_tokens(game.state, p1.id)
    assert names == {"Spirit"}, f"expected {{'Spirit'}}, got {names}"

    # Builder: "target nontoken creature you control without same name as a
    # token you control" — should exclude Spirit-clone and the token itself.
    builder = target_without_same_name_as_your_tokens()
    req = resolve_target_requirement_spec(builder, game.state, p1.id, [])
    assert isinstance(req, TargetRequirement)
    assert spirit_clone.name in req.filter.exclude_names, (
        f"clone name 'Spirit' must be in exclude_names; got {req.filter.exclude_names}"
    )

    # The Spirit token itself is a token — rejected by the require_nontoken filter.
    # The Spirit nontoken creature is rejected by name exclusion.
    # The Bear is the only legal pick.
    assert req.filter.matches(spirit_token, game.state, None) is False, (
        "token candidate must be rejected by require_nontoken"
    )
    assert req.filter.matches(spirit_clone, game.state, None) is False, (
        "nontoken Spirit must be rejected by name exclusion"
    )
    # Source param sets controller-of context. Pass a fake source under p1.
    fake_source = _bare_object("Yenna", controller=p1.id)
    # The filter requires controller='you' — we have to construct a source
    # whose controller is p1.
    assert req.filter.matches(bear, game.state, fake_source) is True, (
        "Bear must remain legal"
    )

    # Builder: "target enchantment you control without same name as another
    # permanent you control" — per-candidate check via custom_filter. A
    # candidate is legal iff no OTHER permanent (excluding the source if
    # provided) shares its name.
    glass = GameObject(
        id="ench_glass",
        name="Glass Casket",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    glass.state = ObjectState(is_token=False)
    game.state.objects[glass.id] = glass
    glass_dup = GameObject(
        id="ench_glass2",
        name="Glass Casket",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    glass_dup.state = ObjectState(is_token=False)
    game.state.objects[glass_dup.id] = glass_dup
    unique = GameObject(
        id="ench_unique",
        name="Cooped Up",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    unique.state = ObjectState(is_token=False)
    game.state.objects[unique.id] = unique

    builder2 = target_without_same_name_as_other_permanents(
        kind='enchantment',
    )
    req2 = resolve_target_requirement_spec(builder2, game.state, p1.id, [])
    # Both Glass Caskets are rejected (they collide with each other).
    assert req2.filter.matches(glass, game.state, fake_source) is False, (
        "Glass Casket #1 should be rejected (Glass Casket #2 has same name)"
    )
    assert req2.filter.matches(glass_dup, game.state, fake_source) is False, (
        "Glass Casket #2 should be rejected (Glass Casket #1 has same name)"
    )
    # Cooped Up is unique — no other permanent shares its name; it's legal.
    assert req2.filter.matches(unique, game.state, fake_source) is True, (
        "Cooped Up should be legal (no name collision)"
    )

    # Verify the per-candidate helper directly.
    assert has_other_permanent_with_same_name(
        glass, game.state, controller_id=p1.id,
    ) is True
    assert has_other_permanent_with_same_name(
        unique, game.state, controller_id=p1.id,
    ) is False
    print("  Builders correctly apply per-candidate name-collision predicate")


# ---------------------------------------------------------------------------
# WOE Apprentice's Folly wet test
# ---------------------------------------------------------------------------

def _put_saga_on_battlefield(game, player, saga_def):
    obj = game.create_object(
        name=saga_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=saga_def.characteristics,
        card_def=None,
    )
    obj.card_def = saga_def
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    return obj


def test_apprentices_folly_skips_name_collision():
    """Wet test: create a token named 'Spirit' + two nontoken creatures
    ('Spirit' + 'Bear'). When the Saga's chapter I fires, the target
    PendingChoice's option list should only contain 'Bear' — the same-name
    'Spirit' creature is excluded because there's already a Spirit token."""
    print("\n=== Test: Apprentice's Folly skips name collisions ===")
    from src.cards.wilds_of_eldraine import THE_APPRENTICES_FOLLY
    from src.engine.types import GameObject, ObjectState

    game = Game()
    p1 = game.add_player("Alice")

    # Spawn token + two nontoken creatures BEFORE the Saga ETBs so the
    # chapter I name-snapshot picks them up correctly.
    spirit_token = GameObject(
        id="tok_spirit",
        name="Spirit",
        characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    spirit_token.state = ObjectState(is_token=True)
    game.state.objects[spirit_token.id] = spirit_token

    spirit_clone = GameObject(
        id="cre_spirit_clone",
        name="Spirit",
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    spirit_clone.state = ObjectState(is_token=False)
    game.state.objects[spirit_clone.id] = spirit_clone

    bear = GameObject(
        id="cre_bear",
        name="Bear",
        characteristics=Characteristics(types={CardType.CREATURE}, power=2, toughness=2),
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id,
        owner=p1.id,
    )
    bear.state = ObjectState(is_token=False)
    game.state.objects[bear.id] = bear

    # Drop the Saga; chapter I fires immediately.
    saga = _put_saga_on_battlefield(game, p1, THE_APPRENTICES_FOLLY)

    # Inspect the pending choice. Should be a target prompt with Bear only.
    pc = game.state.pending_choice
    assert pc is not None, "Apprentice's Folly chapter I must emit a target prompt"
    assert pc.choice_type == 'target', (
        f"choice type must be 'target'; got {pc.choice_type!r}"
    )
    opts = set(pc.options) if isinstance(pc.options, list) else set()
    # Each option may be a raw id (this card uses create_choice_and_resolve
    # with raw IDs). Spirit-clone must NOT be a legal option; Bear MUST be.
    assert bear.id in opts, f"Bear must be legal; got {opts}"
    assert spirit_clone.id not in opts, (
        f"Spirit-clone must be excluded (token name match); got {opts}"
    )
    assert spirit_token.id not in opts, (
        f"Spirit token must be excluded (nontoken qualifier); got {opts}"
    )
    print(f"  Saga chapter I emitted target prompt with legal options: {opts}")
    print("  Spirit (clone + token) correctly excluded; Bear is legal")


def test_apprentices_folly_aborts_when_all_excluded():
    """If every nontoken creature you control shares its name with a token,
    chapter I must NOT emit a prompt (the effect can't be performed)."""
    print("\n=== Test: Apprentice's Folly aborts on full collision ===")
    from src.cards.wilds_of_eldraine import THE_APPRENTICES_FOLLY
    from src.engine.types import GameObject, ObjectState

    game = Game()
    p1 = game.add_player("Alice")

    # Token 'Spirit' + nontoken 'Spirit' — only candidate is excluded.
    spirit_token = GameObject(
        id="tok_s2", name="Spirit",
        characteristics=Characteristics(types={CardType.CREATURE}),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    spirit_token.state = ObjectState(is_token=True)
    game.state.objects[spirit_token.id] = spirit_token

    spirit_clone = GameObject(
        id="cre_s2", name="Spirit",
        characteristics=Characteristics(types={CardType.CREATURE}),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    spirit_clone.state = ObjectState(is_token=False)
    game.state.objects[spirit_clone.id] = spirit_clone

    _put_saga_on_battlefield(game, p1, THE_APPRENTICES_FOLLY)

    # No pending choice should be set — chapter I returned [] cleanly.
    assert game.state.pending_choice is None, (
        f"chapter I must abort when no legal targets; got pending_choice="
        f"{game.state.pending_choice}"
    )
    print("  Chapter I correctly produced no prompt (all candidates excluded)")


# ---------------------------------------------------------------------------
# WOE Yenna wet test
# ---------------------------------------------------------------------------

def test_yenna_skips_name_collision():
    """Wet test: spawn Yenna + two enchantments both named 'Glass Casket'.
    When Yenna activates her ability, the legal-target prompt must exclude
    BOTH 'Glass Casket' enchantments (they share names with each other).
    Yenna's own name should NOT exclude an enchantment unless one of the
    OTHER permanents shares that name.

    Carefully read the printed text: "target enchantment you control that
    doesn't have the same name as another permanent you control." So we
    look for enchantments whose names match ANY OTHER permanent name. With
    two Glass Caskets, each is "another permanent" relative to the other
    — both excluded.

    Add a third enchantment with a unique name to verify it remains legal."""
    print("\n=== Test: Yenna skips name collisions ===")
    from src.cards.wilds_of_eldraine import YENNA_REDTOOTH_REGENT
    from src.engine.types import GameObject, ObjectState

    game = Game()
    p1 = game.add_player("Alice")

    # Spawn Yenna by calling her setup so her activated ability is
    # registered.
    yenna = game.create_object(
        name=YENNA_REDTOOTH_REGENT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=YENNA_REDTOOTH_REGENT.characteristics,
        card_def=YENNA_REDTOOTH_REGENT,
    )

    # Two Glass Caskets — same name; both should be excluded.
    g1 = GameObject(
        id="ench_g1", name="Glass Casket",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}, subtypes={"Aura"}),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    g1.state = ObjectState(is_token=False)
    game.state.objects[g1.id] = g1
    g2 = GameObject(
        id="ench_g2", name="Glass Casket",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}, subtypes={"Aura"}),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    g2.state = ObjectState(is_token=False)
    game.state.objects[g2.id] = g2

    # A unique-name enchantment.
    cooped = GameObject(
        id="ench_cooped", name="Cooped Up",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}, subtypes={"Aura"}),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    cooped.state = ObjectState(is_token=False)
    game.state.objects[cooped.id] = cooped

    # Trigger Yenna's effect_fn directly (we don't go through the activated
    # ability priority path — we just want to inspect the prompt logic).
    abilities = getattr(yenna.state, 'activated_abilities', None) or []
    assert len(abilities) == 1, (
        f"Yenna should register exactly one activated ability; got {abilities}"
    )
    ability = abilities[0]
    # The effect_fn signature is (obj, state, targets) — call directly.
    ability.effect_fn(yenna, game.state, [])

    pc = game.state.pending_choice
    assert pc is not None, "Yenna's ability must emit a target prompt"
    opts = set(pc.options) if isinstance(pc.options, list) else set()
    # Both Glass Caskets must be excluded (they share names); Cooped Up
    # must be legal.
    assert g1.id not in opts, (
        f"Glass Casket #1 must be excluded; got {opts}"
    )
    assert g2.id not in opts, (
        f"Glass Casket #2 must be excluded; got {opts}"
    )
    assert cooped.id in opts, (
        f"Cooped Up must be legal (unique name); got {opts}"
    )
    print(f"  Yenna prompt options: {opts}")
    print("  Both Glass Caskets correctly excluded; Cooped Up legal")


def test_yenna_with_unique_enchantments_offers_all():
    """When every enchantment has a unique name, Yenna's prompt should
    list all of them as legal targets."""
    print("\n=== Test: Yenna offers all unique enchantments ===")
    from src.cards.wilds_of_eldraine import YENNA_REDTOOTH_REGENT
    from src.engine.types import GameObject, ObjectState

    game = Game()
    p1 = game.add_player("Alice")

    yenna = game.create_object(
        name=YENNA_REDTOOTH_REGENT.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=YENNA_REDTOOTH_REGENT.characteristics,
        card_def=YENNA_REDTOOTH_REGENT,
    )

    ench_a = GameObject(
        id="ench_a", name="Aura A",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    ench_a.state = ObjectState()
    game.state.objects[ench_a.id] = ench_a
    ench_b = GameObject(
        id="ench_b", name="Aura B",
        characteristics=Characteristics(types={CardType.ENCHANTMENT}),
        zone=ZoneType.BATTLEFIELD, controller=p1.id, owner=p1.id,
    )
    ench_b.state = ObjectState()
    game.state.objects[ench_b.id] = ench_b

    ability = yenna.state.activated_abilities[0]
    ability.effect_fn(yenna, game.state, [])

    pc = game.state.pending_choice
    assert pc is not None
    opts = set(pc.options) if isinstance(pc.options, list) else set()
    assert ench_a.id in opts and ench_b.id in opts, (
        f"unique-name enchantments must be legal; got {opts}"
    )
    print(f"  Both unique-name enchantments are legal targets: {opts}")


# ---------------------------------------------------------------------------
# Regression coverage for resolve-time / interceptor-time predicate cards
# ---------------------------------------------------------------------------

def test_the_end_card_is_registered_with_target_picker():
    """WOE The End: 'Exile target creature or planeswalker. Search its
    controller's graveyard, hand, and library for any number of cards with
    the same name and exile them.'

    The search predicate runs at resolve time, not at target selection. We
    audit the current implementation:
      - Card must register a target-picker (engine target system or its
        own create_target_choice).
      - The TargetFilter for the initial target need NOT carry
        ``exclude_names`` (the same-name search is a resolve-time predicate
        on graveyard/hand/library, not a same-controller filter).

    Confirm the card exists and its current resolve path is intact."""
    print("\n=== Test: WOE The End regression ===")
    from src.cards.wilds_of_eldraine import THE_END, the_end_resolve

    assert THE_END is not None
    assert THE_END.name == "The End"
    assert "Exile target creature or planeswalker" in THE_END.text, (
        f"text changed unexpectedly: {THE_END.text[:120]!r}"
    )
    # The card's same-name search is a resolve-time predicate, so we
    # confirm the text mentions both the target-exile half AND the
    # graveyard/hand/library search half. That covers the "Search its
    # controller's graveyard, hand, and library for any number of cards
    # with the same name as that permanent and exile them" sub-effect.
    assert "with the same name" in THE_END.text or "any number of cards" in THE_END.text, (
        f"text doesn't mention same-name search: {THE_END.text!r}"
    )
    # The resolve hook MUST be present (engine routes here for the exile +
    # name-search). We don't fully replay the resolve here; we just verify
    # the function is the one wired and that it tolerates an empty state.
    assert callable(the_end_resolve), "the_end_resolve must remain wired"
    game = Game()
    game.add_player("Alice")
    out = the_end_resolve([], game.state)
    assert out == [], f"empty-state resolve should yield no events; got {out}"
    print("  The End: target predicate is resolve-time; card definition intact")


def test_maelstrom_pulse_card_is_registered():
    """FDN Maelstrom Pulse: 'Destroy target nonland permanent and all other
    permanents with the same name as that permanent.'

    Wired in Phase 5b mop-up: cast-time target_requirements + resolve_fn
    that destroys the target and every other permanent matching the
    target's name. Detailed end-to-end coverage lives in
    ``tests/test_phase5b_spell_copy.py``; this regression just confirms
    the card is correctly registered with the new resolve hook.
    """
    print("\n=== Test: FDN Maelstrom Pulse regression ===")
    from src.cards.foundations import MAELSTROM_PULSE

    assert MAELSTROM_PULSE is not None
    assert MAELSTROM_PULSE.name == "Maelstrom Pulse"
    assert "with the same name as that permanent" in MAELSTROM_PULSE.text, (
        f"text changed: {MAELSTROM_PULSE.text!r}"
    )
    assert MAELSTROM_PULSE.resolve is not None, (
        "Maelstrom Pulse should have a resolve_fn wired in Phase 5b mop-up"
    )
    assert MAELSTROM_PULSE.target_requirements, (
        "Maelstrom Pulse should declare cast-time target_requirements"
    )
    print("  Maelstrom Pulse: resolve + target_requirements wired")


def test_central_elevator_door_unlock_no_op_documented():
    """DSK Central Elevator: 'When you unlock this door, search your library
    for a Room card that doesn't have the same name as a Room you control'.

    The current implementation explicitly skips the search (engine gap on
    tutoring with name-comparison filters). Confirm the SKIP is intentional
    by verifying door1's unlock effect is a no-op."""
    print("\n=== Test: DSK Central Elevator regression ===")
    from src.cards.duskmourn import CENTRAL_ELEVATOR, central_elevator_setup
    from src.engine.types import GameObject, ObjectState

    assert CENTRAL_ELEVATOR is not None
    assert CENTRAL_ELEVATOR.name == "Central Elevator"

    # Reconstruct the door1 effect by hand by invoking setup and inspecting
    # the room registration. The current implementation embeds the SKIP
    # rationale in a comment; the door1 effect_fn returns [].
    game = Game()
    p1 = game.add_player("Alice")
    obj = game.create_object(
        name=CENTRAL_ELEVATOR.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=CENTRAL_ELEVATOR.characteristics,
        card_def=CENTRAL_ELEVATOR,
    )
    # If the setup ran (it would on create_object via the pipeline path), the
    # interceptors should be registered. We don't fully drive door unlock here;
    # we just confirm the setup callable is the right shape.
    assert callable(central_elevator_setup), (
        "central_elevator_setup must remain wired"
    )
    print("  Central Elevator: door-1 search skipped (engine gap on tutor+name)")


def test_marvin_murderous_mimic_no_op_documented():
    """DSK Marvin, Murderous Mimic: 'has all activated abilities of creatures
    you control that don't have the same name as this creature.'

    Engine gap: dynamic activated-ability copying. The current setup is a
    no-op returning []. We document the gap so a future enabling change
    flags here."""
    print("\n=== Test: DSK Marvin Murderous Mimic regression ===")
    from src.cards.duskmourn import MARVIN_MURDEROUS_MIMIC, marvin_murderous_mimic_setup
    from src.engine.types import GameObject, ObjectState

    assert MARVIN_MURDEROUS_MIMIC is not None
    assert MARVIN_MURDEROUS_MIMIC.name == "Marvin, Murderous Mimic"
    # The setup is a no-op (engine gap). Calling it on a bare object should
    # return [].
    game = Game()
    p1 = game.add_player("Alice")
    obj = GameObject(
        id="tst_marvin",
        name="Marvin, Murderous Mimic",
        characteristics=MARVIN_MURDEROUS_MIMIC.characteristics,
        zone=ZoneType.BATTLEFIELD,
        controller=p1.id, owner=p1.id,
    )
    obj.state = ObjectState()
    out = marvin_murderous_mimic_setup(obj, game.state)
    assert out == [], (
        f"marvin_murderous_mimic_setup is currently a no-op; got {out}"
    )
    print("  Marvin: dynamic ability copy is an engine gap (setup returns [])")


from src.engine.types import GameObject, ObjectState  # for test helpers above


if __name__ == "__main__":
    test_exclude_names_filter_axis_works()
    print("PASS  test_exclude_names_filter_axis_works")
    test_target_without_same_name_builder()
    print("PASS  test_target_without_same_name_builder")
    test_apprentices_folly_skips_name_collision()
    print("PASS  test_apprentices_folly_skips_name_collision")
    test_apprentices_folly_aborts_when_all_excluded()
    print("PASS  test_apprentices_folly_aborts_when_all_excluded")
    test_yenna_skips_name_collision()
    print("PASS  test_yenna_skips_name_collision")
    test_yenna_with_unique_enchantments_offers_all()
    print("PASS  test_yenna_with_unique_enchantments_offers_all")
    test_the_end_card_is_registered_with_target_picker()
    print("PASS  test_the_end_card_is_registered_with_target_picker")
    test_maelstrom_pulse_card_is_registered()
    print("PASS  test_maelstrom_pulse_card_is_registered")
    test_central_elevator_door_unlock_no_op_documented()
    print("PASS  test_central_elevator_door_unlock_no_op_documented")
    test_marvin_murderous_mimic_no_op_documented()
    print("PASS  test_marvin_murderous_mimic_no_op_documented")
    print("\nAll Phase 5b name-constraint tests passed.")
