"""
Phase 5b Agent J — spell-copy modes + Maelstrom Pulse name-based destruction.

Card-side wirings (no engine changes):

THREE_STEPS_AHEAD (`src/cards/outlaws_thunder_junction.py`) — 3 Spree modes:
  + {1}  — Until EOT, target creature you control gets +1/+1 and has
            flash, hexproof, ward {2}.
  + {2}  — Draw three cards.
  + {3}  — Create a copy of this spell (emits COPY_STACK_ITEM).

RETURN_THE_FAVOR (`src/cards/outlaws_thunder_junction.py`) — Phase 5b regular
instant. ``target_requirements`` accepts an opposing INSTANT or SORCERY spell
on the stack; resolve emits COPY_STACK_ITEM.

MAELSTROM_PULSE (`src/cards/foundations.py`) — Phase 5b sorcery.
``target_requirements`` accepts a nonland permanent; resolve emits one
OBJECT_DESTROYED per battlefield permanent (including the target itself)
whose name matches the target's name.

Run directly:
    python tests/test_phase5b_spell_copy.py
"""

import asyncio
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, Characteristics,
    PlayerAction, ActionType,
    SpreeMode, get_spree_modes, is_spree_card,
    make_instant, make_creature,
)
from src.engine.stack import StackItem, StackItemType
from src.engine.targeting import Target

from src.cards import outlaws_thunder_junction as otj
from src.cards import foundations as fdn


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_phase5b_otj_spree_final.py)
# ---------------------------------------------------------------------------


def make_two_player_game():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    return game, p1, p2


def add_mana(game, player_id, color="C", amount=1):
    from src.engine.mana import ManaType
    color_to_type = {
        "W": ManaType.WHITE,
        "U": ManaType.BLUE,
        "B": ManaType.BLACK,
        "R": ManaType.RED,
        "G": ManaType.GREEN,
        "C": ManaType.COLORLESS,
    }
    mtype = color_to_type[color]
    game.mana_system.produce_mana(player_id, mtype, amount)


def _coerce_test_targets(targets, state):
    """Mirror server._coerce_action_targets for tests: list[list[str|Target]]
    → list[list[Target]]. Avoids 'str object has no attribute is_player'
    errors when card resolves call ``_flatten_targets`` (which expects
    ``Target`` instances)."""
    if not targets:
        return []
    coerced = []
    for group in targets:
        if not group:
            coerced.append([])
            continue
        grp = []
        for entry in group:
            if isinstance(entry, Target):
                grp.append(entry)
                continue
            tid = entry if isinstance(entry, str) else getattr(entry, 'id', str(entry))
            grp.append(Target(id=tid, is_player=(tid in state.players)))
        coerced.append(grp)
    return coerced


def cast_spell(game, player_id, spell_obj, targets=None):
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=player_id,
        card_id=spell_obj.id,
        targets=_coerce_test_targets(targets, game.state),
    )
    cast_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    emitted = []
    for ev in cast_events or []:
        emitted.extend(game.emit(ev))
    return cast_events + emitted


def make_spell(game, owner_id, card_def, zone=ZoneType.HAND):
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def submit_spree(game, player_id, indices):
    choice = game.state.pending_choice
    assert choice is not None, "expected pending Spree choice"
    payload = [{"index": i} for i in indices]
    return game.submit_choice(choice.id, player_id, payload)


def submit_target(game, player_id, target_id):
    choice = game.state.pending_choice
    assert choice is not None, "expected pending target choice"
    return game.submit_choice(choice.id, player_id, [target_id])


def make_bear(game, owner_id, name="Bear", power=2, toughness=2, subtypes=None):
    if subtypes is None:
        subtypes = set()
    bear_def = make_creature(
        name=name, power=power, toughness=toughness,
        mana_cost="{2}", colors=set(),
        subtypes=subtypes,
    )
    return game.create_object(
        name=name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=bear_def.characteristics, card_def=bear_def,
    )


def make_battlefield_object(game, owner_id, *, name, types, subtypes=None,
                            power=None, toughness=None, colors=None,
                            token=False):
    """Spawn a permanent directly on the battlefield without going through a
    card_def. Used to set up "three creatures named Goblin" scenarios for
    Maelstrom Pulse tests."""
    chars = Characteristics(
        types=set(types),
        subtypes=set(subtypes or set()),
        colors=set(colors or set()),
        power=power,
        toughness=toughness,
    )
    obj = game.create_object(
        name=name, owner_id=owner_id, zone=ZoneType.BATTLEFIELD,
        characteristics=chars,
    )
    if token:
        # token flag is observed by some engine paths; store on the object.
        obj.is_token = True
    return obj


# ---------------------------------------------------------------------------
# 1. THREE_STEPS_AHEAD — Spree modes
# ---------------------------------------------------------------------------


def test_three_steps_ahead_registers_three_modes():
    """Sanity: setup_interceptors registers the 3 brief-described modes."""
    print("\n=== Test: Three Steps Ahead registers 3 Spree modes ===")
    game, p1, _ = make_two_player_game()
    obj = game.create_object(
        name=otj.THREE_STEPS_AHEAD.name,
        owner_id=p1.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=otj.THREE_STEPS_AHEAD.characteristics,
        card_def=otj.THREE_STEPS_AHEAD,
    )
    assert is_spree_card(obj)
    modes = get_spree_modes(obj)
    assert len(modes) == 3, f"expected 3 modes, got {len(modes)}"
    # Verify by mode names ordered (pump, draw, copy).
    names = [m.name for m in modes]
    assert names[0].startswith("Pump"), names
    assert "Draw" in names[1], names
    assert "Copy this spell" in names[2], names
    print(f"OK: Three Steps Ahead modes: {names}")


def test_three_steps_ahead_pump_mode():
    """Mode 0 (+{1}): pump target creature +1/+1 and grant flash/hexproof/ward EOT."""
    print("\n=== Test: Three Steps Ahead pump mode ===")
    game, p1, _ = make_two_player_game()
    my_bear = make_bear(game, p1.id, name="My Bear")
    spell = make_spell(game, p1.id, otj.THREE_STEPS_AHEAD)
    add_mana(game, p1.id, "U", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0])  # pump
    pre = game.stack.resolve_top()
    pc = game.state.pending_choice
    assert pc is not None, "expected target prompt for pump mode"
    assert my_bear.id in pc.options
    ok, msg, events = submit_target(game, p1.id, my_bear.id)
    assert ok, msg

    # PT_MODIFICATION +1/+1 EOT on bear.
    pt_mods = [e for e in events
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('object_id') == my_bear.id
               and e.payload.get('power_mod') == 1
               and e.payload.get('toughness_mod') == 1]
    assert pt_mods, f"expected +1/+1; got {[e.payload for e in events if e.type == EventType.PT_MODIFICATION]}"
    # GRANT_KEYWORD flash, hexproof, ward.
    keywords = {e.payload.get('keyword') for e in events
                if e.type == EventType.GRANT_KEYWORD
                and e.payload.get('object_id') == my_bear.id}
    assert 'flash' in keywords, f"expected flash; got {keywords}"
    assert 'hexproof' in keywords, f"expected hexproof; got {keywords}"
    assert 'ward' in keywords, f"expected ward; got {keywords}"
    print(f"OK: Three Steps Ahead pump emitted +1/+1 + {keywords}")


def test_three_steps_ahead_draw_mode():
    """Mode 1 (+{2}): draw three cards (no target)."""
    print("\n=== Test: Three Steps Ahead draw mode ===")
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, otj.THREE_STEPS_AHEAD)
    add_mana(game, p1.id, "U", 1)
    add_mana(game, p1.id, "C", 2)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [1])  # draw three
    events = game.stack.resolve_top()
    draws = [e for e in events
             if e.type == EventType.DRAW
             and e.payload.get('amount') == 3
             and e.payload.get('player') == p1.id]
    assert draws, f"expected DRAW 3 for p1; got {[e.payload for e in events if e.type == EventType.DRAW]}"
    print("OK: Three Steps Ahead drew 3 cards")


def test_three_steps_ahead_copy_mode_emits_stack_copy():
    """Mode 2 (+{3}): create a copy of this spell.

    The resolve_fn pushes a fresh ``is_copy=True`` StackItem mirroring the
    resolving spell (card_id / controller_id / resolve_fn). This is the
    mid-resolve workaround for ``StackManager.resolve_top`` having already
    popped the original ``StackItem`` (see in-source comment in
    ``_three_steps_ahead_copy_this_spell``)."""
    print("\n=== Test: Three Steps Ahead copy-this-spell mode ===")
    game, p1, _ = make_two_player_game()
    spell = make_spell(game, p1.id, otj.THREE_STEPS_AHEAD)
    add_mana(game, p1.id, "U", 1)
    add_mana(game, p1.id, "C", 3)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [2])  # copy this spell
    # Pre-resolve: the spell is on the stack as a StackItem (size 1).
    assert game.stack.size() == 1
    events = game.stack.resolve_top()
    # After resolve_top: the original was popped, but the copy-this-spell
    # mode manually pushed a copy back. Stack size returns to 1.
    assert game.stack.size() == 1, (
        f"expected the copy on stack; stack size={game.stack.size()}"
    )
    top = game.stack.top()
    assert top is not None
    assert top.is_copy is True, "top of stack must be the spell copy"
    assert top.card_id == spell.id, \
        "copy must reference the resolving spell's card_id"
    print(f"OK: Three Steps Ahead pushed a stack copy ({top.id})")


def test_three_steps_ahead_all_modes():
    """Pay all 3 costs ({U}+{1}+{2}+{3}={U}+{6}): pump + draw 3 + copy."""
    print("\n=== Test: Three Steps Ahead all three modes ===")
    game, p1, _ = make_two_player_game()
    my_bear = make_bear(game, p1.id, name="My Bear")
    spell = make_spell(game, p1.id, otj.THREE_STEPS_AHEAD)
    # {U} base + {1} pump + {2} draw + {3} copy = {U} + 6 generic
    add_mana(game, p1.id, "U", 1)
    add_mana(game, p1.id, "C", 6)
    cast_spell(game, p1.id, spell)
    submit_spree(game, p1.id, [0, 1, 2])  # all three
    # Pre-resolve: the spell is on top.
    assert game.stack.size() == 1
    pre = game.stack.resolve_top()
    # Mode 0 (pump) takes a target.
    pc = game.state.pending_choice
    assert pc is not None, "expected target prompt for pump mode"
    ok, msg, events = submit_target(game, p1.id, my_bear.id)
    assert ok, msg

    # The events returned from submit_target include only the pump-mode
    # events that fired BEFORE the next mode's choice opens. Spree chains
    # remaining modes after each targeted-mode resolves; non-targeted modes
    # fire inline. Verify pump + draw via emitted events list.
    pt_mods = [e for e in events
               if e.type == EventType.PT_MODIFICATION
               and e.payload.get('object_id') == my_bear.id]
    draws = [e for e in events
             if e.type == EventType.DRAW
             and e.payload.get('amount') == 3]
    assert pt_mods, "expected PT_MODIFICATION from pump mode"
    assert draws, "expected DRAW 3 from draw mode"
    # The copy-this-spell mode pushes a fresh StackItem directly (see
    # in-source rationale). Verify the stack now has a copy on top.
    assert game.stack.size() >= 1, "expected the copy on stack"
    top = game.stack.top()
    assert top is not None and top.is_copy is True, \
        f"expected copy on top of stack; got {top}"
    assert top.card_id == spell.id, \
        f"copy must reference the spell's card_id; got {top.card_id}"
    print("OK: Three Steps Ahead all three modes fired (pump + draw + copy)")


# ---------------------------------------------------------------------------
# 2. RETURN_THE_FAVOR — regular instant, target opposing spell, copy it
# ---------------------------------------------------------------------------


def test_return_the_favor_declares_target_requirements():
    """RETURN_THE_FAVOR has target_requirements (instant + sorcery, opponent)."""
    print("\n=== Test: Return the Favor target_requirements ===")
    reqs = otj.RETURN_THE_FAVOR.target_requirements
    assert reqs is not None and len(reqs) == 1, f"expected 1 req; got {reqs}"
    req = reqs[0]
    flt = req.filter
    assert flt.types is not None
    assert CardType.INSTANT in flt.types and CardType.SORCERY in flt.types
    assert flt.controller == 'opponent', \
        f"expected controller='opponent'; got {flt.controller}"
    # Zones must include STACK.
    assert ZoneType.STACK in (flt.zones or []), \
        f"expected zones=[STACK]; got {flt.zones}"
    print("OK: Return the Favor target_requirements: instant/sorcery on stack, opponent's")


def _push_dummy_spell(game, controller_id, *, name="Lava Coil",
                      types=None, can_be_copied=True):
    """Push a fake spell stack item for tests."""
    types = set(types or {CardType.INSTANT})
    card = game.create_object(
        name=name,
        owner_id=controller_id,
        zone=ZoneType.STACK,
        characteristics=Characteristics(types=types),
    )

    def _resolve_noop(_t, _s):
        return []

    item = StackItem(
        id="",
        type=StackItemType.SPELL,
        source_id=card.id,
        controller_id=controller_id,
        card_id=card.id,
        resolve_fn=_resolve_noop,
        can_be_copied=can_be_copied,
    )
    game.stack.push(item)
    return card, item


def test_return_the_favor_copies_opponent_spell():
    """Cast Return the Favor targeting an opposing instant on the stack;
    verify a COPY_STACK_ITEM event is produced for the opposing spell."""
    print("\n=== Test: Return the Favor copies opposing instant ===")
    game, p1, p2 = make_two_player_game()

    # P2 has a Lava-Coil-like instant on the stack.
    opp_card, opp_item = _push_dummy_spell(
        game, p2.id, name="Lava Coil", types={CardType.INSTANT},
    )

    # P1 casts Return the Favor with target pre-supplied (opp's spell).
    spell = make_spell(game, p1.id, otj.RETURN_THE_FAVOR)
    add_mana(game, p1.id, "R", 2)
    cast_spell(game, p1.id, spell, targets=[[opp_card.id]])

    # Spell should be on top of the stack (above the opp's spell).
    assert game.stack.top().card_id == spell.id, \
        f"expected Return the Favor on top; got {game.stack.top()}"
    # Stack: [opp_lava_coil, return_the_favor]
    assert game.stack.size() == 2

    events = game.stack.resolve_top()
    copy_events = [e for e in events if e.type == EventType.COPY_STACK_ITEM]
    assert copy_events, f"expected COPY_STACK_ITEM; got {[e.type for e in events]}"
    sid = copy_events[0].payload.get('stack_item_id')
    assert sid == opp_item.id, f"expected copy of opponent's spell ({opp_item.id}); got {sid}"

    # Emit the event so the handler actually pushes the copy.
    for ev in events:
        game.emit(ev)
    # Now the stack should have: [opp_original, opp_copy]
    assert game.stack.size() == 2
    top = game.stack.top()
    assert top.is_copy is True
    assert top.card_id == opp_card.id, "copy must reference the same card_id"
    print("OK: Return the Favor produced a stack copy of the opponent's spell")


def test_return_the_favor_aborts_with_no_legal_targets():
    """No opposing spells on the stack → cast aborts (no PendingChoice, no
    payment, card stays in hand)."""
    print("\n=== Test: Return the Favor aborts when no legal targets ===")
    game, p1, p2 = make_two_player_game()

    # No spells on stack; p1's own spell on stack does NOT count (opponent
    # filter). Even if p1 has an instant on the stack, filter rejects it.
    spell = make_spell(game, p1.id, otj.RETURN_THE_FAVOR)
    add_mana(game, p1.id, "R", 2)
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    # Cast aborted: no PendingChoice, card still in hand.
    assert game.state.pending_choice is None, \
        "no PendingChoice expected when no legal targets"
    assert spell.zone == ZoneType.HAND, \
        f"card should remain in hand; got {spell.zone}"
    print("OK: Return the Favor aborted cleanly with no opposing spell")


def test_return_the_favor_filter_rejects_own_spell():
    """Even with a controlled (own) spell on the stack, the opponent filter
    rejects it as a target — caster can't copy their own spell."""
    print("\n=== Test: Return the Favor rejects own spell ===")
    game, p1, p2 = make_two_player_game()
    # P1 has their own instant on the stack — should NOT be a legal target.
    own_card, own_item = _push_dummy_spell(
        game, p1.id, name="Own Instant", types={CardType.INSTANT},
    )

    spell = make_spell(game, p1.id, otj.RETURN_THE_FAVOR)
    add_mana(game, p1.id, "R", 2)
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=p1.id,
        card_id=spell.id,
        targets=[],
    )
    asyncio.run(game.priority_system._handle_cast_spell(action))
    # Either: (a) no legal targets → cast aborts, OR (b) the choice was
    # emitted with the own_card filtered out. Both confirm the filter
    # works. We accept either path since a single illegal target yields
    # no PendingChoice (engine's "no legal targets → abort").
    pc = game.state.pending_choice
    if pc is not None:
        option_ids = {opt["id"] for opt in pc.options}
        assert own_card.id not in option_ids, \
            f"own spell must not be a legal target; got options {option_ids}"
        print("OK: own spell excluded from PendingChoice options")
    else:
        # Cast aborted — perfect, filter rejected the only candidate.
        assert spell.zone == ZoneType.HAND
        print("OK: cast aborted (own spell was the only candidate)")


# ---------------------------------------------------------------------------
# 3. MAELSTROM_PULSE — destroy target nonland permanent + all same-named
# ---------------------------------------------------------------------------


def test_maelstrom_pulse_declares_target_requirements():
    print("\n=== Test: Maelstrom Pulse target_requirements ===")
    reqs = fdn.MAELSTROM_PULSE.target_requirements
    assert reqs is not None and len(reqs) == 1
    req = reqs[0]
    # Filter must use custom nonland filter; not exposed cleanly but we can
    # spot-check by trying to match a land vs a creature.
    print(f"OK: Maelstrom Pulse has {len(reqs)} target requirement")


def test_maelstrom_pulse_destroys_target_and_same_named():
    """3 creatures named 'Goblin', target one — all 3 destroyed."""
    print("\n=== Test: Maelstrom Pulse destroys target + same-named ===")
    game, p1, p2 = make_two_player_game()

    g1 = make_battlefield_object(
        game, p1.id, name="Goblin",
        types={CardType.CREATURE}, subtypes={"Goblin"},
        power=1, toughness=1, colors={Color.RED},
    )
    g2 = make_battlefield_object(
        game, p1.id, name="Goblin",
        types={CardType.CREATURE}, subtypes={"Goblin"},
        power=1, toughness=1, colors={Color.RED},
    )
    g3 = make_battlefield_object(
        game, p2.id, name="Goblin",
        types={CardType.CREATURE}, subtypes={"Goblin"},
        power=1, toughness=1, colors={Color.RED},
    )

    spell = make_spell(game, p1.id, fdn.MAELSTROM_PULSE)
    add_mana(game, p1.id, "B", 1)
    add_mana(game, p1.id, "G", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell, targets=[[g1.id]])
    events = game.stack.resolve_top()

    destroyed_ids = {e.payload.get('object_id') for e in events
                     if e.type == EventType.OBJECT_DESTROYED}
    assert destroyed_ids == {g1.id, g2.id, g3.id}, (
        f"expected all 3 Goblins destroyed; got {destroyed_ids}"
    )
    print(f"OK: Maelstrom Pulse destroyed all 3 Goblins")


def test_maelstrom_pulse_ignores_different_names():
    """Target 'Goblin'; other permanents with different names survive."""
    print("\n=== Test: Maelstrom Pulse ignores different-named permanents ===")
    game, p1, p2 = make_two_player_game()
    goblin = make_battlefield_object(
        game, p1.id, name="Goblin",
        types={CardType.CREATURE}, subtypes={"Goblin"},
        power=1, toughness=1, colors={Color.RED},
    )
    elf = make_battlefield_object(
        game, p1.id, name="Elf",
        types={CardType.CREATURE}, subtypes={"Elf"},
        power=1, toughness=1, colors={Color.GREEN},
    )
    angel = make_battlefield_object(
        game, p2.id, name="Angel",
        types={CardType.CREATURE}, subtypes={"Angel"},
        power=4, toughness=4, colors={Color.WHITE},
    )

    spell = make_spell(game, p1.id, fdn.MAELSTROM_PULSE)
    add_mana(game, p1.id, "B", 1)
    add_mana(game, p1.id, "G", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell, targets=[[goblin.id]])
    events = game.stack.resolve_top()

    destroyed_ids = {e.payload.get('object_id') for e in events
                     if e.type == EventType.OBJECT_DESTROYED}
    assert destroyed_ids == {goblin.id}, (
        f"expected only the Goblin destroyed; got {destroyed_ids}"
    )
    print("OK: Maelstrom Pulse destroyed only the Goblin (Elf + Angel survived)")


def test_maelstrom_pulse_ignores_tokens_of_different_name():
    """Token named 'Spirit' on board; target a 'Goblin' creature — only the
    Goblin (and any same-named Goblins) gets destroyed."""
    print("\n=== Test: Maelstrom Pulse ignores tokens of different name ===")
    game, p1, p2 = make_two_player_game()
    goblin = make_battlefield_object(
        game, p1.id, name="Goblin",
        types={CardType.CREATURE}, subtypes={"Goblin"},
        power=1, toughness=1, colors={Color.RED},
    )
    spirit_token = make_battlefield_object(
        game, p1.id, name="Spirit",
        types={CardType.CREATURE}, subtypes={"Spirit"},
        power=1, toughness=1, colors={Color.WHITE}, token=True,
    )
    # Add a second Goblin token, also a token but with the SAME name — it
    # should also be destroyed. This catches a bug where the resolver only
    # destroys non-tokens.
    goblin_token = make_battlefield_object(
        game, p2.id, name="Goblin",
        types={CardType.CREATURE}, subtypes={"Goblin"},
        power=1, toughness=1, colors={Color.RED}, token=True,
    )

    spell = make_spell(game, p1.id, fdn.MAELSTROM_PULSE)
    add_mana(game, p1.id, "B", 1)
    add_mana(game, p1.id, "G", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell, targets=[[goblin.id]])
    events = game.stack.resolve_top()

    destroyed_ids = {e.payload.get('object_id') for e in events
                     if e.type == EventType.OBJECT_DESTROYED}
    assert spirit_token.id not in destroyed_ids, \
        f"Spirit token must survive; got {destroyed_ids}"
    assert goblin.id in destroyed_ids
    assert goblin_token.id in destroyed_ids, \
        f"same-named token must also be destroyed; got {destroyed_ids}"
    print(
        f"OK: Maelstrom Pulse destroyed both Goblins (incl. token), Spirit survived"
    )


def test_maelstrom_pulse_does_not_destroy_lands():
    """Even if a land has the same name as the target (e.g., target 'Goblin'
    and there are no same-named lands), lands are excluded categorically.
    Here we set up a land + a creature; target the creature; verify only the
    creature dies."""
    print("\n=== Test: Maelstrom Pulse never destroys lands ===")
    game, p1, _ = make_two_player_game()
    creature = make_battlefield_object(
        game, p1.id, name="Mox Sapphire",
        types={CardType.ARTIFACT}, subtypes=set(),
        colors=set(),
    )
    # A land named identically to the creature shouldn't be hit even though
    # it shares the name (lands are excluded). MTG corner case but worth a
    # guard.
    land = make_battlefield_object(
        game, p1.id, name="Mox Sapphire",
        types={CardType.LAND, CardType.ARTIFACT}, subtypes=set(),
    )

    spell = make_spell(game, p1.id, fdn.MAELSTROM_PULSE)
    add_mana(game, p1.id, "B", 1)
    add_mana(game, p1.id, "G", 1)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, spell, targets=[[creature.id]])
    events = game.stack.resolve_top()

    destroyed_ids = {e.payload.get('object_id') for e in events
                     if e.type == EventType.OBJECT_DESTROYED}
    assert creature.id in destroyed_ids, \
        f"target nonland permanent should be destroyed; got {destroyed_ids}"
    assert land.id not in destroyed_ids, \
        f"land must not be destroyed by Maelstrom Pulse; got {destroyed_ids}"
    print("OK: Maelstrom Pulse spared the land")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_three_steps_ahead_registers_three_modes,
        test_three_steps_ahead_pump_mode,
        test_three_steps_ahead_draw_mode,
        test_three_steps_ahead_copy_mode_emits_stack_copy,
        test_three_steps_ahead_all_modes,
        test_return_the_favor_declares_target_requirements,
        test_return_the_favor_copies_opponent_spell,
        test_return_the_favor_aborts_with_no_legal_targets,
        test_return_the_favor_filter_rejects_own_spell,
        test_maelstrom_pulse_declares_target_requirements,
        test_maelstrom_pulse_destroys_target_and_same_named,
        test_maelstrom_pulse_ignores_different_names,
        test_maelstrom_pulse_ignores_tokens_of_different_name,
        test_maelstrom_pulse_does_not_destroy_lands,
    ]
    passed = 0
    failed: list[tuple[str, str]] = []
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            import traceback
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
    if failed:
        for name, err in failed:
            print(f"  FAIL {name}: {err}")
        sys.exit(1)
