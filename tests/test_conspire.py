"""
Tests for the Shadowmoor / Lorwyn Conspire mechanic (CR 702.78, W29).

Conspire never appears as printed text in this codebase — it's always *granted*
by a permanent ability ("Each <filtered> spell you cast has conspire."). The
three cards exercising the grant in the codebase are:
    - lorwyn_eclipsed.RAIDING_SCHEMES (noncreature spells)
    - fae_but_mid.RAIDING_SCHEMES (noncreature spells)
    - fae_but_mid.WORT_THE_RAIDMOTHER (red-or-green instants/sorceries)

Coverage
--------
1. ConspireGrant: registry registration + cleanup on source leaving.
2. find_color_share_creatures: untapped + controller + color overlap.
3. find_conspire_grants_for_spell: filter dispatch + multi-grant.
4. Cast pipeline opens conspire prompt (with stub human handler).
5. Accepting conspire taps two creatures + emits CONSPIRE_TRIGGERED + COPY_STACK_ITEM.
6. Declining conspire (empty submit) emits no copy.
7. No two color-sharing creatures = no prompt opened.
8. Color-share enforcement at submit time: mismatched colors rejected.
9. Wort filter: only red/green instants/sorceries get the prompt.
10. Permanent spell copy ends up on stack as is_copy (token-conversion is
    an engine gap; documented).
11. Auto-decline path: no human handler = no prompt opens.
12. Per-card smoke test: all three wired cards register their grants.
"""

import asyncio
import os
import sys

# Run from the repo root regardless of which worktree the tests live in.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    PlayerAction, ActionType, ManaCost,
    make_creature, make_instant, make_enchantment, make_sorcery,
)
from src.engine.conspire import (
    ConspireGrant,
    grant_conspire,
    list_active_grants,
    find_conspire_grants_for_spell,
    find_color_share_creatures,
    open_conspire_prompt,
)
from src.cards.interceptor_helpers import make_conspire_grant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_two_player_game():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")
    return game, p1, p2


def add_mana(game, player_id, color="C", amount=1):
    """Inject mana into a player's pool for tests."""
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


def cast_spell(game, player_id, spell_obj):
    """Drive a CAST_SPELL action and emit the resulting events."""
    action = PlayerAction(
        type=ActionType.CAST_SPELL,
        player_id=player_id,
        card_id=spell_obj.id,
    )
    cast_events = asyncio.run(game.priority_system._handle_cast_spell(action))
    emitted = []
    for ev in cast_events or []:
        emitted.extend(game.emit(ev))
    return cast_events + emitted


def make_card(game, owner_id, card_def, zone=ZoneType.HAND):
    return game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def attach_stub_human_handler(game):
    """Attach a no-op human-action handler so the conspire hook doesn't
    auto-decline (which it does when no human is wired up).
    """
    async def _stub(player_id, legal_actions):
        # Tests drive the choice via submit_choice; this handler is never
        # actually invoked, but its presence is enough to disable the
        # auto-decline path.
        return None
    game.priority_system.get_human_action = _stub


def submit_conspire(game, player_id, selected):
    """Submit a conspire choice. ``selected`` may be [] (decline) or a list
    of two creature ids (accept).
    """
    choice = game.state.pending_choice
    assert choice is not None, "expected pending conspire choice"
    assert choice.choice_type == "conspire", f"expected conspire; got {choice.choice_type}"
    return game.submit_choice(choice.id, player_id, selected)


# ---------------------------------------------------------------------------
# 1. ConspireGrant registry
# ---------------------------------------------------------------------------


def test_grant_conspire_registers_on_install():
    print("\n=== Test: grant_conspire registers grant on install ===")
    game, p1, _ = make_two_player_game()
    enchant_def = make_enchantment(
        name="Test Enchant",
        mana_cost="{R}",
        colors={Color.RED},
        text="Each noncreature spell you cast has conspire.",
        setup_interceptors=lambda obj, state: [
            make_conspire_grant(
                obj, state,
                spell_filter=lambda s, _st: CardType.CREATURE not in s.characteristics.types,
            )
        ],
    )
    src = make_card(game, p1.id, enchant_def, zone=ZoneType.BATTLEFIELD)
    grants = list_active_grants(game.state)
    assert len(grants) == 1, f"expected 1 grant; got {len(grants)}"
    assert grants[0].source_id == src.id
    assert grants[0].controller == p1.id
    print("OK: grant registered")


def test_grant_conspire_unregisters_on_zone_leave():
    print("\n=== Test: grant unregisters when source leaves battlefield ===")
    game, p1, _ = make_two_player_game()
    enchant_def = make_enchantment(
        name="Test Enchant",
        mana_cost="{R}",
        colors={Color.RED},
        text="Each noncreature spell you cast has conspire.",
        setup_interceptors=lambda obj, state: [
            make_conspire_grant(
                obj, state,
                spell_filter=lambda s, _st: CardType.CREATURE not in s.characteristics.types,
            )
        ],
    )
    src = make_card(game, p1.id, enchant_def, zone=ZoneType.BATTLEFIELD)
    assert len(list_active_grants(game.state)) == 1

    # Move source to graveyard (simulating destruction).
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': src.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=src.id,
    ))
    grants = list_active_grants(game.state)
    assert len(grants) == 0, f"expected grant cleaned up; got {len(grants)}"
    print("OK: grant cleaned up on zone leave")


# ---------------------------------------------------------------------------
# 2. find_color_share_creatures
# ---------------------------------------------------------------------------


def test_find_color_share_creatures_filters_correctly():
    print("\n=== Test: find_color_share_creatures filtering ===")
    game, p1, p2 = make_two_player_game()

    red_creature = make_creature(
        name="Red Goblin", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    green_creature = make_creature(
        name="Green Elf", power=1, toughness=1, mana_cost="{G}",
        colors={Color.GREEN},
    )
    blue_creature = make_creature(
        name="Blue Drake", power=2, toughness=2, mana_cost="{1}{U}",
        colors={Color.BLUE},
    )

    r1 = make_card(game, p1.id, red_creature, zone=ZoneType.BATTLEFIELD)
    r2 = make_card(game, p1.id, red_creature, zone=ZoneType.BATTLEFIELD)
    g1 = make_card(game, p1.id, green_creature, zone=ZoneType.BATTLEFIELD)
    u1 = make_card(game, p1.id, blue_creature, zone=ZoneType.BATTLEFIELD)
    p2_red = make_card(game, p2.id, red_creature, zone=ZoneType.BATTLEFIELD)

    # Tap one of p1's red creatures.
    r2.state.tapped = True

    # Searching for RED creatures — only p1's untapped reds should match.
    legal = find_color_share_creatures(game.state, p1.id, {Color.RED})
    legal_ids = {c.id for c in legal}
    assert r1.id in legal_ids, "r1 (untapped red) should match"
    assert r2.id not in legal_ids, "r2 (tapped) should NOT match"
    assert g1.id not in legal_ids, "g1 (green) should NOT match"
    assert u1.id not in legal_ids, "u1 (blue) should NOT match"
    assert p2_red.id not in legal_ids, "p2_red (opponent's) should NOT match"
    print(f"OK: matched {len(legal)} creatures (expected 1)")


def test_find_color_share_creatures_colorless_returns_empty():
    print("\n=== Test: colorless spell -> no color-share creatures ===")
    game, p1, _ = make_two_player_game()
    red_creature = make_creature(
        name="Red Goblin", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    make_card(game, p1.id, red_creature, zone=ZoneType.BATTLEFIELD)
    legal = find_color_share_creatures(game.state, p1.id, set())
    assert legal == [], f"colorless spell shares no colors; got {len(legal)}"
    print("OK: colorless spell yields no legal creatures")


def test_find_color_share_creatures_multicolor():
    print("\n=== Test: multi-color creature satisfies either color ===")
    game, p1, _ = make_two_player_game()
    multicolor = make_creature(
        name="Wort, the Raidmother", power=3, toughness=3,
        mana_cost="{4}{R/G}{R/G}",
        colors={Color.RED, Color.GREEN},
    )
    obj = make_card(game, p1.id, multicolor, zone=ZoneType.BATTLEFIELD)
    legal_for_red = find_color_share_creatures(game.state, p1.id, {Color.RED})
    legal_for_green = find_color_share_creatures(game.state, p1.id, {Color.GREEN})
    assert obj in legal_for_red, "RG creature satisfies a red spell"
    assert obj in legal_for_green, "RG creature satisfies a green spell"
    print("OK: multi-color creature counts for either color")


# ---------------------------------------------------------------------------
# 3. find_conspire_grants_for_spell dispatches the filter
# ---------------------------------------------------------------------------


def test_find_conspire_grants_filters_by_spell_filter():
    print("\n=== Test: find_conspire_grants_for_spell honours the filter ===")
    game, p1, _ = make_two_player_game()

    # Wort-style filter: only RG instants/sorceries.
    def rg_filter(spell, _st):
        types = spell.characteristics.types
        if not (CardType.INSTANT in types or CardType.SORCERY in types):
            return False
        cs = spell.characteristics.colors or set()
        return Color.RED in cs or Color.GREEN in cs

    src_def = make_creature(
        name="Wort, the Raidmother", power=3, toughness=3,
        mana_cost="{4}{R/G}{R/G}",
        colors={Color.RED, Color.GREEN},
        setup_interceptors=lambda obj, state: [
            make_conspire_grant(obj, state, spell_filter=rg_filter)
        ],
    )
    make_card(game, p1.id, src_def, zone=ZoneType.BATTLEFIELD)

    # A red instant — should match.
    bolt = make_instant(
        name="Lightning Bolt", mana_cost="{R}", colors={Color.RED},
    )
    bolt_obj = make_card(game, p1.id, bolt, zone=ZoneType.STACK)
    matched = find_conspire_grants_for_spell(game.state, p1.id, bolt_obj)
    assert len(matched) == 1, f"red instant should match Wort; got {len(matched)}"

    # A blue instant — should NOT match.
    cancel = make_instant(
        name="Cancel", mana_cost="{1}{U}{U}", colors={Color.BLUE},
    )
    cancel_obj = make_card(game, p1.id, cancel, zone=ZoneType.STACK)
    matched2 = find_conspire_grants_for_spell(game.state, p1.id, cancel_obj)
    assert len(matched2) == 0, f"blue instant should NOT match Wort; got {len(matched2)}"

    # A red CREATURE (Wort applies to instants/sorceries only).
    goblin = make_creature(
        name="Mogg Fanatic", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    goblin_obj = make_card(game, p1.id, goblin, zone=ZoneType.STACK)
    matched3 = find_conspire_grants_for_spell(game.state, p1.id, goblin_obj)
    assert len(matched3) == 0, f"creature spell should NOT match Wort; got {len(matched3)}"
    print("OK: filter dispatch is correct")


# ---------------------------------------------------------------------------
# 4. Cast pipeline opens prompt (with stub human handler)
# ---------------------------------------------------------------------------


def _build_raiding_schemes_state():
    """Return (game, p1, p2, schemes_obj) with Raiding Schemes on the bf."""
    game, p1, p2 = make_two_player_game()
    attach_stub_human_handler(game)

    schemes_def = make_enchantment(
        name="Raiding Schemes",
        mana_cost="{3}{R}{G}",
        colors={Color.RED, Color.GREEN},
        text="Each noncreature spell you cast has conspire.",
        setup_interceptors=lambda obj, state: [
            make_conspire_grant(
                obj, state,
                spell_filter=lambda s, _st: CardType.CREATURE not in s.characteristics.types,
            )
        ],
    )
    schemes = make_card(game, p1.id, schemes_def, zone=ZoneType.BATTLEFIELD)
    return game, p1, p2, schemes


def test_conspire_prompt_opens_for_noncreature_spell():
    print("\n=== Test: Conspire prompt opens for a noncreature spell ===")
    game, p1, _p2, _schemes = _build_raiding_schemes_state()

    # Two red creatures so the conspire cost is payable.
    goblin = make_creature(
        name="Mogg Fanatic", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    g1 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g2 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g1.state.summoning_sickness = False
    g2.state.summoning_sickness = False

    # Cast a red instant (Lightning Bolt).
    bolt = make_instant(
        name="Lightning Bolt", mana_cost="{R}", colors={Color.RED},
        text="Lightning Bolt deals 3 damage to any target.",
    )
    bolt_obj = make_card(game, p1.id, bolt)
    add_mana(game, p1.id, "R", 1)
    cast_spell(game, p1.id, bolt_obj)

    pc = game.state.pending_choice
    assert pc is not None, "expected a conspire prompt"
    assert pc.choice_type == "conspire", f"got {pc.choice_type}"
    assert pc.player == p1.id
    option_ids = {o["id"] for o in pc.options}
    assert g1.id in option_ids and g2.id in option_ids, (
        f"both red creatures should be options; got {option_ids}"
    )
    print(f"OK: prompt has {len(pc.options)} options")


# ---------------------------------------------------------------------------
# 5. Accepting conspire taps + emits COPY_STACK_ITEM
# ---------------------------------------------------------------------------


def test_conspire_accept_taps_creatures_and_copies_spell():
    print("\n=== Test: accepting conspire taps + copies ===")
    game, p1, _p2, _schemes = _build_raiding_schemes_state()

    goblin = make_creature(
        name="Mogg Fanatic", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    g1 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g2 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g1.state.summoning_sickness = False
    g2.state.summoning_sickness = False

    bolt = make_instant(
        name="Lightning Bolt", mana_cost="{R}", colors={Color.RED},
    )
    bolt_obj = make_card(game, p1.id, bolt)
    add_mana(game, p1.id, "R", 1)

    pre_stack_size = game.stack.size()
    cast_spell(game, p1.id, bolt_obj)
    # Bolt should be on the stack now.
    assert game.stack.size() == pre_stack_size + 1, (
        f"expected stack size {pre_stack_size + 1}; got {game.stack.size()}"
    )

    # Accept conspire by submitting both goblin ids.
    ok, err, events = submit_conspire(game, p1.id, [g1.id, g2.id])
    assert ok, f"submit failed: {err}"

    # Both goblins should be tapped.
    assert g1.state.tapped, "g1 should be tapped"
    assert g2.state.tapped, "g2 should be tapped"

    # CONSPIRE_TRIGGERED marker emitted.
    cm = [e for e in events if e.type == EventType.CONSPIRE_TRIGGERED]
    assert len(cm) == 1, f"expected 1 CONSPIRE_TRIGGERED; got {len(cm)}"
    assert sorted(cm[0].payload['tapped']) == sorted([g1.id, g2.id])

    # The COPY_STACK_ITEM event should have produced a copy on the stack.
    # Stack now contains: bolt (original) + bolt copy = pre_stack_size + 2.
    assert game.stack.size() == pre_stack_size + 2, (
        f"expected stack size {pre_stack_size + 2}; got {game.stack.size()}"
    )
    top = game.stack.top()
    assert getattr(top, 'is_copy', False) is True, "top of stack should be the copy"
    print("OK: tapped both, COPY_STACK_ITEM produced a copy on the stack")


# ---------------------------------------------------------------------------
# 6. Declining conspire (empty submit) emits no copy
# ---------------------------------------------------------------------------


def test_conspire_decline_no_copy_no_taps():
    print("\n=== Test: declining conspire = no copy, no taps ===")
    game, p1, _p2, _schemes = _build_raiding_schemes_state()

    goblin = make_creature(
        name="Mogg Fanatic", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    g1 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g2 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g1.state.summoning_sickness = False
    g2.state.summoning_sickness = False

    bolt = make_instant(
        name="Lightning Bolt", mana_cost="{R}", colors={Color.RED},
    )
    bolt_obj = make_card(game, p1.id, bolt)
    add_mana(game, p1.id, "R", 1)

    pre_stack_size = game.stack.size()
    cast_spell(game, p1.id, bolt_obj)
    assert game.state.pending_choice is not None

    ok, err, events = submit_conspire(game, p1.id, [])
    assert ok, f"decline submit failed: {err}"

    assert not g1.state.tapped, "g1 should NOT be tapped on decline"
    assert not g2.state.tapped, "g2 should NOT be tapped on decline"
    cm = [e for e in events if e.type == EventType.CONSPIRE_TRIGGERED]
    assert cm == [], f"expected no CONSPIRE_TRIGGERED; got {len(cm)}"
    # Stack should only have the original (one copy was NOT added).
    assert game.stack.size() == pre_stack_size + 1
    print("OK: decline produced no copy, no taps")


# ---------------------------------------------------------------------------
# 7. No two color-sharing creatures = no prompt
# ---------------------------------------------------------------------------


def test_conspire_no_prompt_if_only_one_legal_creature():
    print("\n=== Test: only one color-sharing creature -> no prompt ===")
    game, p1, _p2, _schemes = _build_raiding_schemes_state()

    # Only ONE red creature — Conspire requires TWO.
    goblin = make_creature(
        name="Mogg Fanatic", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    g1 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g1.state.summoning_sickness = False

    bolt = make_instant(
        name="Lightning Bolt", mana_cost="{R}", colors={Color.RED},
    )
    bolt_obj = make_card(game, p1.id, bolt)
    add_mana(game, p1.id, "R", 1)
    cast_spell(game, p1.id, bolt_obj)

    assert game.state.pending_choice is None, (
        f"no conspire prompt should open; got {game.state.pending_choice}"
    )
    print("OK: no prompt when fewer than 2 color-sharing creatures")


# ---------------------------------------------------------------------------
# 8. Color-share enforced at submit (mismatched colors rejected)
# ---------------------------------------------------------------------------


def test_conspire_mismatched_color_rejected_on_submit():
    print("\n=== Test: submit with non-matching color is rejected ===")
    game, p1, _p2, _schemes = _build_raiding_schemes_state()

    red_def = make_creature(
        name="Red Goblin", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    green_def = make_creature(
        name="Green Elf", power=1, toughness=1, mana_cost="{G}",
        colors={Color.GREEN},
    )
    r1 = make_card(game, p1.id, red_def, zone=ZoneType.BATTLEFIELD)
    g1 = make_card(game, p1.id, green_def, zone=ZoneType.BATTLEFIELD)
    # Need a second green or second red so the prompt opens for a red spell.
    # The helper requires at least 2 color-sharing creatures: with one red +
    # one green, only one creature shares a color with a red bolt, so no
    # prompt opens. Add another green creature to keep the count high but
    # the colors mismatched (still won't open since only 1 red shares).
    # Instead, add a second red so prompt opens, then try to submit one red
    # + one green and confirm the green is rejected.
    r2 = make_card(game, p1.id, red_def, zone=ZoneType.BATTLEFIELD)
    for c in (r1, g1, r2):
        c.state.summoning_sickness = False

    bolt = make_instant(
        name="Lightning Bolt", mana_cost="{R}", colors={Color.RED},
    )
    bolt_obj = make_card(game, p1.id, bolt)
    add_mana(game, p1.id, "R", 1)
    cast_spell(game, p1.id, bolt_obj)

    pc = game.state.pending_choice
    assert pc is not None, "expected prompt with 2 reds available"
    # The options should be the two reds (g1 doesn't share a color).
    option_ids = {o["id"] for o in pc.options}
    assert r1.id in option_ids and r2.id in option_ids
    assert g1.id not in option_ids, "green elf should NOT be a legal option"

    # Try to submit r1 + g1 (g1 isn't even an option, but force-submit to
    # test the validation path). The handler should reject.
    ok, err, _ = submit_conspire(game, p1.id, [r1.id, g1.id])
    # PendingChoice.validate_selection only checks that selected items are
    # in options; since g1 isn't in options the validation will fail at
    # that level. Either way, no copy/tap should result.
    assert not r1.state.tapped, "r1 should NOT be tapped on a rejected submit"
    assert not g1.state.tapped, "g1 should NOT be tapped on a rejected submit"
    print(f"OK: rejected submit (ok={ok}, err={err!r})")


# ---------------------------------------------------------------------------
# 9. Wort filter: blue spells get NO conspire prompt
# ---------------------------------------------------------------------------


def test_wort_filter_blue_spell_no_prompt():
    print("\n=== Test: Wort filter rejects blue instants ===")
    game, p1, _p2 = make_two_player_game()
    attach_stub_human_handler(game)

    def rg_filter(spell, _st):
        types = spell.characteristics.types
        if not (CardType.INSTANT in types or CardType.SORCERY in types):
            return False
        cs = spell.characteristics.colors or set()
        return Color.RED in cs or Color.GREEN in cs

    wort_def = make_creature(
        name="Wort, the Raidmother", power=3, toughness=3,
        mana_cost="{4}{R/G}{R/G}",
        colors={Color.RED, Color.GREEN},
        setup_interceptors=lambda obj, state: [
            make_conspire_grant(obj, state, spell_filter=rg_filter)
        ],
    )
    make_card(game, p1.id, wort_def, zone=ZoneType.BATTLEFIELD)

    # Two blue creatures so creature count would be sufficient if the
    # filter accepted blue (it shouldn't).
    blue_def = make_creature(
        name="Blue Drake", power=2, toughness=2, mana_cost="{1}{U}",
        colors={Color.BLUE},
    )
    b1 = make_card(game, p1.id, blue_def, zone=ZoneType.BATTLEFIELD)
    b2 = make_card(game, p1.id, blue_def, zone=ZoneType.BATTLEFIELD)
    for c in (b1, b2):
        c.state.summoning_sickness = False

    # Cast a blue instant; Wort's grant should NOT apply.
    cancel = make_instant(
        name="Cancel", mana_cost="{1}{U}{U}", colors={Color.BLUE},
    )
    cancel_obj = make_card(game, p1.id, cancel)
    add_mana(game, p1.id, "U", 2)
    add_mana(game, p1.id, "C", 1)
    cast_spell(game, p1.id, cancel_obj)

    assert game.state.pending_choice is None, (
        f"Wort grant must reject blue spells; got prompt {game.state.pending_choice}"
    )
    print("OK: Wort skipped the blue spell")


# ---------------------------------------------------------------------------
# 10. Permanent spell copy is on stack as is_copy=True
#    (CR 702.78: "A copy of a permanent spell becomes a token." The token-
#    becoming behaviour is an engine gap; this test pins down the current
#    is_copy state of the copy.)
# ---------------------------------------------------------------------------


def test_conspire_permanent_spell_copy_is_marked_is_copy():
    print("\n=== Test: copy of a permanent spell is is_copy=True ===")
    # We use a generic conspire grant that allows ALL spells (not just
    # noncreature) so we can test a creature spell. (Real Conspire grants
    # in the codebase target noncreature spells; this is exercising the
    # mechanic's lower-level behavior.)
    game, p1, _p2 = make_two_player_game()
    attach_stub_human_handler(game)

    src_def = make_enchantment(
        name="All-Spells Conspire",
        mana_cost="{0}",
        colors={Color.RED, Color.GREEN},
        setup_interceptors=lambda obj, state: [
            make_conspire_grant(obj, state, spell_filter=lambda s, _st: True)
        ],
    )
    make_card(game, p1.id, src_def, zone=ZoneType.BATTLEFIELD)

    # Two red creatures so we can pay conspire on a red creature spell.
    goblin = make_creature(
        name="Mogg Fanatic", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    g1 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g2 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    for c in (g1, g2):
        c.state.summoning_sickness = False

    # Cast a red creature.
    creature_to_cast = make_card(game, p1.id, goblin)
    add_mana(game, p1.id, "R", 1)

    pre_stack_size = game.stack.size()
    cast_spell(game, p1.id, creature_to_cast)
    pc = game.state.pending_choice
    assert pc is not None, "expected conspire prompt"

    ok, err, _ = submit_conspire(game, p1.id, [g1.id, g2.id])
    assert ok, f"submit failed: {err}"

    # Stack now: original creature spell + copy = +2.
    assert game.stack.size() == pre_stack_size + 2
    top = game.stack.top()
    assert getattr(top, 'is_copy', False), "top should be a copy"
    # CR 702.78: a copy of a permanent spell becomes a token. The token
    # conversion is an engine gap; we only confirm the is_copy mark today
    # so future work has a regression handle.
    print("OK: permanent-spell copy is is_copy=True (token-conversion is a tracked engine gap)")


# ---------------------------------------------------------------------------
# 11. Auto-decline path: no human handler -> no prompt
# ---------------------------------------------------------------------------


def test_conspire_auto_declines_when_no_human_handler():
    print("\n=== Test: auto-decline when no human handler is wired ===")
    game, p1, _p2 = make_two_player_game()
    # Deliberately do NOT attach a human handler.

    schemes_def = make_enchantment(
        name="Raiding Schemes",
        mana_cost="{3}{R}{G}",
        colors={Color.RED, Color.GREEN},
        setup_interceptors=lambda obj, state: [
            make_conspire_grant(
                obj, state,
                spell_filter=lambda s, _st: CardType.CREATURE not in s.characteristics.types,
            )
        ],
    )
    make_card(game, p1.id, schemes_def, zone=ZoneType.BATTLEFIELD)

    goblin = make_creature(
        name="Mogg Fanatic", power=1, toughness=1, mana_cost="{R}",
        colors={Color.RED},
    )
    g1 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    g2 = make_card(game, p1.id, goblin, zone=ZoneType.BATTLEFIELD)
    for c in (g1, g2):
        c.state.summoning_sickness = False

    bolt = make_instant(
        name="Lightning Bolt", mana_cost="{R}", colors={Color.RED},
    )
    bolt_obj = make_card(game, p1.id, bolt)
    add_mana(game, p1.id, "R", 1)
    pre_stack = game.stack.size()
    cast_spell(game, p1.id, bolt_obj)

    assert game.state.pending_choice is None, (
        f"auto-decline should suppress the prompt; got {game.state.pending_choice}"
    )
    # Stack: only the original Bolt (no copy made).
    assert game.stack.size() == pre_stack + 1, (
        f"only original should be on stack; got {game.stack.size()}"
    )
    assert not g1.state.tapped and not g2.state.tapped
    print("OK: auto-decline path leaves stack untouched")


# ---------------------------------------------------------------------------
# 12. Smoke test: all three wired cards register their grants
# ---------------------------------------------------------------------------


def test_wired_cards_register_grants():
    print("\n=== Test: wired cards register conspire grants on ETB ===")
    from src.cards.lorwyn_eclipsed import RAIDING_SCHEMES as ECLIPSED_RAIDING
    from src.cards.custom.fae_but_mid import (
        RAIDING_SCHEMES as CUSTOM_RAIDING,
        WORT_THE_RAIDMOTHER,
    )

    for label, card_def in [
        ("Eclipsed RAIDING_SCHEMES", ECLIPSED_RAIDING),
        ("Custom RAIDING_SCHEMES", CUSTOM_RAIDING),
        ("Custom WORT_THE_RAIDMOTHER", WORT_THE_RAIDMOTHER),
    ]:
        game, p1, _ = make_two_player_game()
        make_card(game, p1.id, card_def, zone=ZoneType.BATTLEFIELD)
        grants = list_active_grants(game.state)
        assert len(grants) >= 1, f"{label}: expected a grant; got {grants}"
        print(f"  OK: {label} registered {len(grants)} grant(s)")
    print("OK: all three wired cards register their conspire grants")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


TESTS = [
    test_grant_conspire_registers_on_install,
    test_grant_conspire_unregisters_on_zone_leave,
    test_find_color_share_creatures_filters_correctly,
    test_find_color_share_creatures_colorless_returns_empty,
    test_find_color_share_creatures_multicolor,
    test_find_conspire_grants_filters_by_spell_filter,
    test_conspire_prompt_opens_for_noncreature_spell,
    test_conspire_accept_taps_creatures_and_copies_spell,
    test_conspire_decline_no_copy_no_taps,
    test_conspire_no_prompt_if_only_one_legal_creature,
    test_conspire_mismatched_color_rejected_on_submit,
    test_wort_filter_blue_spell_no_prompt,
    test_conspire_permanent_spell_copy_is_marked_is_copy,
    test_conspire_auto_declines_when_no_human_handler,
    test_wired_cards_register_grants,
]


def main():
    failures = []
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            failures.append((t.__name__, str(e)))
            print(f"  FAIL: {t.__name__}: {e}")
        except Exception as e:
            import traceback
            failures.append((t.__name__, traceback.format_exc()))
            print(f"  ERROR: {t.__name__}: {e}")
    print()
    print(f"Conspire tests: ran {len(TESTS)}, "
          f"passed {len(TESTS) - len(failures)}, failed {len(failures)}")
    if failures:
        for name, err in failures:
            print(f"  - {name}: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
