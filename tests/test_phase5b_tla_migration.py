"""
Phase 5b cast-time targeting migration — Avatar: The Last Airbender (TLA)

Each TLA spell whose resolve_fn previously called ``create_target_choice``
inline has been refactored to consume the ``targets`` parameter directly,
and the corresponding ``CardDefinition`` now declares ``target_requirements``
so the priority system emits a PendingChoice at cast time when the cast
action arrives without pre-supplied targets.

This file exercises the end-to-end engine flow for representative TLA cards:
- ``test_<card>_emits_pending_choice_on_empty_cast``: cast with empty targets
  → engine emits the right PendingChoice with the legal options.
- ``test_<card>_handler_completes_cast``: submit the choice → spell pushes
  to the stack with chosen targets.
- ``test_<card>_resolve_consumes_targets_directly``: invoke the resolve_fn
  with pre-supplied targets[0] → assert the right Events emit (no internal
  PendingChoice is created).
"""

import asyncio
import os
import sys

# Make project root importable regardless of where pytest runs from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
)
from src.engine.priority import PlayerAction, ActionType
from src.engine.targeting import Target
from src.engine.game import make_land
from src.cards.test_cards import SOUL_WARDEN
from src.cards.avatar_tla import (
    ENTER_THE_AVATAR_STATE,
    OCTOPUS_FORM,
    COMBUSTION_TECHNIQUE,
    PILLAR_LAUNCH,
    THE_LAST_AGNI_KAI,
    ROCKY_REBUKE,
    ALLIES_AT_LAST,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game_with_lands_for(card_def, p1_name="P1", p2_name="P2",
                              num_plains=1, num_islands=0, num_mountains=0,
                              num_forests=0, num_swamps=0):
    """Build a fresh two-player game with the chosen lands in play for P1
    plus ``card_def`` in P1's hand. Returns (game, p1, p2, card_obj)."""
    game = Game()
    p1 = game.add_player(p1_name)
    p2 = game.add_player(p2_name)

    card_obj = game.create_object(
        name=card_def.name,
        owner_id=p1.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )

    def _add_lands(subtype, n):
        for _ in range(n):
            ld = make_land(subtype, subtypes={subtype})
            game.create_object(
                name=subtype, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
                characteristics=ld.characteristics, card_def=ld,
            )

    _add_lands("Plains", num_plains)
    _add_lands("Island", num_islands)
    _add_lands("Mountain", num_mountains)
    _add_lands("Forest", num_forests)
    _add_lands("Swamp", num_swamps)
    return game, p1, p2, card_obj


def _add_creature(game, owner_id, name="Bear"):
    return game.create_object(
        name=name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=SOUL_WARDEN.characteristics,
        card_def=SOUL_WARDEN,
    )


# ---------------------------------------------------------------------------
# ENTER_THE_AVATAR_STATE — target creature you control
# ---------------------------------------------------------------------------

def test_enter_the_avatar_state_emits_pending_choice_on_empty_cast():
    """Cast with empty targets → PendingChoice listing P1's creatures only
    (controller='you' filter excludes opponent creatures)."""
    game, p1, p2, card = _make_game_with_lands_for(
        ENTER_THE_AVATAR_STATE, num_plains=1
    )
    own = _add_creature(game, p1.id, "Aang")
    opp = _add_creature(game, p2.id, "Bear")

    assert game.state.pending_choice is None
    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=card.id,
        targets=[],
    )
    events = asyncio.run(game.priority_system._handle_cast_spell(action))
    assert events == [] or not events
    pc = game.state.pending_choice
    assert pc is not None, "expected PendingChoice for Enter the Avatar State"
    assert pc.choice_type == "target"
    assert pc.source_id == card.id
    option_ids = {opt["id"] for opt in pc.options}
    assert own.id in option_ids, f"own creature should be legal: {option_ids}"
    assert opp.id not in option_ids, \
        f"opp creature must NOT be legal (controller='you'): {option_ids}"
    # Card still in hand while paused.
    assert card.zone == ZoneType.HAND


def test_enter_the_avatar_state_handler_completes_cast():
    """Submit the choice → spell pushes to the stack with our chosen creature."""
    game, p1, p2, card = _make_game_with_lands_for(
        ENTER_THE_AVATAR_STATE, num_plains=1
    )
    own = _add_creature(game, p1.id, "Aang")
    _add_creature(game, p2.id, "Bear")

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=card.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None
    ok, err, _events = game.submit_choice(pc.id, p1.id, [own.id])
    assert ok, f"submit_choice failed: {err}"
    assert game.state.pending_choice is None
    assert card.zone == ZoneType.STACK, \
        f"card should be on stack after choice completes: {card.zone}"


def test_enter_the_avatar_state_resolve_consumes_targets_directly():
    """Phase 5b: resolve_fn consumes targets[0][0] and emits GRANT_KEYWORD
    events for each of flying/first_strike/lifelink/hexproof. No internal
    PendingChoice is created."""
    game, p1, _p2, card = _make_game_with_lands_for(
        ENTER_THE_AVATAR_STATE, num_plains=1
    )
    own = _add_creature(game, p1.id, "Aang")
    # Push the spell onto the stack so the resolve fn can find it via
    # _tla_caster_and_id.
    card.zone = ZoneType.STACK
    stack = game.state.zones['stack']
    stack.objects.append(card.id)

    targets = [[Target(id=own.id, is_player=False)]]
    events = ENTER_THE_AVATAR_STATE.resolve(targets, game.state)
    assert game.state.pending_choice is None, \
        "resolve_fn must NOT create an internal PendingChoice"
    keywords = [
        e.payload['keyword']
        for e in events if e.type == EventType.GRANT_KEYWORD
        and e.payload.get('object_id') == own.id
    ]
    assert set(keywords) == {'flying', 'first_strike', 'lifelink', 'hexproof'}, \
        f"expected all 4 keywords on own creature, got {keywords}"


# ---------------------------------------------------------------------------
# COMBUSTION_TECHNIQUE — target creature (any)
# ---------------------------------------------------------------------------

def test_combustion_technique_emits_pending_choice():
    """Cast with empty targets → PendingChoice listing ALL creatures
    (no controller restriction)."""
    game, p1, p2, card = _make_game_with_lands_for(
        COMBUSTION_TECHNIQUE, num_mountains=2
    )
    own = _add_creature(game, p1.id, "Zuko")
    opp = _add_creature(game, p2.id, "Azula")

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=card.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None, "expected PendingChoice for Combustion Technique"
    option_ids = {opt["id"] for opt in pc.options}
    assert own.id in option_ids and opp.id in option_ids, \
        f"both creatures should be legal: {option_ids}"


def test_combustion_technique_resolve_consumes_targets_directly():
    """resolve_fn emits DAMAGE to chosen target. Damage = 2 + Lesson cards
    in graveyard."""
    game, p1, p2, card = _make_game_with_lands_for(
        COMBUSTION_TECHNIQUE, num_mountains=2
    )
    target = _add_creature(game, p2.id, "Foe")
    card.zone = ZoneType.STACK
    game.state.zones['stack'].objects.append(card.id)

    targets = [[Target(id=target.id, is_player=False)]]
    events = COMBUSTION_TECHNIQUE.resolve(targets, game.state)
    assert game.state.pending_choice is None
    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    assert len(damage_events) == 1
    assert damage_events[0].payload['target'] == target.id
    # 0 Lessons in GY → 2 base damage.
    assert damage_events[0].payload['amount'] == 2


# ---------------------------------------------------------------------------
# PILLAR_LAUNCH — target creature (any)
# ---------------------------------------------------------------------------

def test_pillar_launch_handler_completes_cast_with_chosen_target():
    """Cast Pillar Launch with empty targets → choose → spell goes to stack."""
    game, p1, _p2, card = _make_game_with_lands_for(
        PILLAR_LAUNCH, num_forests=1
    )
    target = _add_creature(game, p1.id, "Pillar")

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=card.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    pc = game.state.pending_choice
    assert pc is not None
    ok, err, _events = game.submit_choice(pc.id, p1.id, [target.id])
    assert ok, f"submit_choice failed: {err}"
    assert card.zone == ZoneType.STACK


def test_pillar_launch_resolve_emits_pump_and_reach_and_untap():
    """Resolve emits PT_MODIFICATION(+2/+2), GRANT_KEYWORD(reach), UNTAP."""
    game, p1, _p2, card = _make_game_with_lands_for(
        PILLAR_LAUNCH, num_forests=1
    )
    target = _add_creature(game, p1.id, "Pillar")
    card.zone = ZoneType.STACK
    game.state.zones['stack'].objects.append(card.id)

    targets = [[Target(id=target.id, is_player=False)]]
    events = PILLAR_LAUNCH.resolve(targets, game.state)
    assert game.state.pending_choice is None
    types_seen = {e.type for e in events}
    assert EventType.PT_MODIFICATION in types_seen, \
        f"missing PT_MODIFICATION: {types_seen}"
    assert EventType.GRANT_KEYWORD in types_seen, \
        f"missing GRANT_KEYWORD: {types_seen}"
    assert EventType.UNTAP in types_seen, \
        f"missing UNTAP: {types_seen}"


# ---------------------------------------------------------------------------
# THE_LAST_AGNI_KAI — two requirements (your creature + opp creature)
# ---------------------------------------------------------------------------

def test_the_last_agni_kai_emits_choices_for_both_requirements():
    """First PendingChoice = your creatures; submit → second choice =
    opp's creatures."""
    game, p1, p2, card = _make_game_with_lands_for(
        THE_LAST_AGNI_KAI, num_mountains=2
    )
    own = _add_creature(game, p1.id, "Zuko")
    opp = _add_creature(game, p2.id, "Azula")

    action = PlayerAction(
        type=ActionType.CAST_SPELL, player_id=p1.id, card_id=card.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))

    # First choice → your creature only.
    pc1 = game.state.pending_choice
    assert pc1 is not None, "expected first PendingChoice (your creature)"
    option_ids1 = {opt["id"] for opt in pc1.options}
    assert own.id in option_ids1 and opp.id not in option_ids1, \
        f"first choice should list only your creatures: {option_ids1}"
    ok, err, _events = game.submit_choice(pc1.id, p1.id, [own.id])
    assert ok, f"first submit_choice failed: {err}"

    # Second choice → opp creature only.
    pc2 = game.state.pending_choice
    assert pc2 is not None, "expected second PendingChoice (opp creature)"
    option_ids2 = {opt["id"] for opt in pc2.options}
    assert opp.id in option_ids2 and own.id not in option_ids2, \
        f"second choice should list only opp creatures: {option_ids2}"
    ok, err, _events = game.submit_choice(pc2.id, p1.id, [opp.id])
    assert ok, f"second submit_choice failed: {err}"

    assert game.state.pending_choice is None
    assert card.zone == ZoneType.STACK


def test_the_last_agni_kai_resolve_consumes_two_target_groups():
    """resolve_fn emits FIGHT(your, opp) when given two target groups."""
    game, p1, p2, card = _make_game_with_lands_for(
        THE_LAST_AGNI_KAI, num_mountains=2
    )
    own = _add_creature(game, p1.id, "Zuko")
    opp = _add_creature(game, p2.id, "Azula")
    card.zone = ZoneType.STACK
    game.state.zones['stack'].objects.append(card.id)

    targets = [
        [Target(id=own.id, is_player=False)],
        [Target(id=opp.id, is_player=False)],
    ]
    events = THE_LAST_AGNI_KAI.resolve(targets, game.state)
    fight_events = [e for e in events if e.type == EventType.FIGHT]
    assert len(fight_events) == 1
    assert fight_events[0].payload['attacker'] == own.id
    assert fight_events[0].payload['defender'] == opp.id


# ---------------------------------------------------------------------------
# ALLIES_AT_LAST — up to two of your creatures + one opp creature
# ---------------------------------------------------------------------------

def test_allies_at_last_resolve_with_one_attacker_and_target():
    """Resolve emits DAMAGE from each chosen own creature (with power > 0)
    to the chosen opp creature."""
    game, p1, p2, card = _make_game_with_lands_for(
        ALLIES_AT_LAST, num_forests=3
    )
    own = _add_creature(game, p1.id, "Ally")
    opp = _add_creature(game, p2.id, "Foe")
    card.zone = ZoneType.STACK
    game.state.zones['stack'].objects.append(card.id)

    targets = [
        [Target(id=own.id, is_player=False)],
        [Target(id=opp.id, is_player=False)],
    ]
    events = ALLIES_AT_LAST.resolve(targets, game.state)
    damage_events = [e for e in events if e.type == EventType.DAMAGE]
    # Soul Warden is 1/1 so one damage event is expected.
    assert len(damage_events) == 1
    assert damage_events[0].payload['target'] == opp.id
    assert damage_events[0].payload['amount'] == 1  # Soul Warden power = 1


if __name__ == "__main__":
    test_enter_the_avatar_state_emits_pending_choice_on_empty_cast()
    print("PASS  test_enter_the_avatar_state_emits_pending_choice_on_empty_cast")
    test_enter_the_avatar_state_handler_completes_cast()
    print("PASS  test_enter_the_avatar_state_handler_completes_cast")
    test_enter_the_avatar_state_resolve_consumes_targets_directly()
    print("PASS  test_enter_the_avatar_state_resolve_consumes_targets_directly")
    test_combustion_technique_emits_pending_choice()
    print("PASS  test_combustion_technique_emits_pending_choice")
    test_combustion_technique_resolve_consumes_targets_directly()
    print("PASS  test_combustion_technique_resolve_consumes_targets_directly")
    test_pillar_launch_handler_completes_cast_with_chosen_target()
    print("PASS  test_pillar_launch_handler_completes_cast_with_chosen_target")
    test_pillar_launch_resolve_emits_pump_and_reach_and_untap()
    print("PASS  test_pillar_launch_resolve_emits_pump_and_reach_and_untap")
    test_the_last_agni_kai_emits_choices_for_both_requirements()
    print("PASS  test_the_last_agni_kai_emits_choices_for_both_requirements")
    test_the_last_agni_kai_resolve_consumes_two_target_groups()
    print("PASS  test_the_last_agni_kai_resolve_consumes_two_target_groups")
    test_allies_at_last_resolve_with_one_attacker_and_target()
    print("PASS  test_allies_at_last_resolve_with_one_attacker_and_target")
    print("\nAll Phase 5b TLA-migration tests passed.")
