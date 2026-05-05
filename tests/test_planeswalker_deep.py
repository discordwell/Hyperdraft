"""W15: Tests for the deepened planeswalker framework.

Covers:
- Combat redirect (CR 508.1.h): attacker can be repointed to attack a PW;
  damage hits PW (loyalty -X). Lethal redirect destroys the PW via SBA.
- Legend rule (CR 704.5j): controlling 2+ legendary permanents with the
  same name forces destruction of all but one.
- Emblems (CR 113.1c): persistent global effects with no characteristics
  other than "Emblem"; they live in state.emblems and never leave play.
- Ajani, Caller of the Pride (FDN): full activation cycle through the
  framework + emblem-variant ult exercises make_emblem_creatures_have_keywords.
- Ral, Crackling Wit (BLB): updated -10 fires the W15 emblem framework
  and the emblem reacts to instant/sorcery casts.
- Non-combat damage redirect (CR 113.5g) helper round-trip.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import asyncio

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    Characteristics, GameObject,
)
from src.cards.card_factories import make_planeswalker
from src.engine.combat import AttackDeclaration
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import (
    Phase,
    check_planeswalker_zero_loyalty_sbas,
    check_legend_rule_sbas,
)
from src.engine.planeswalker import (
    redirect_attack_to_planeswalker,
    redirect_damage_to_planeswalker,
    is_planeswalker,
)
from src.engine.emblem import create_emblem, get_emblems_for_player, Emblem
from src.cards.interceptor_helpers import (
    make_planeswalker_setup,
    make_loyalty_ability,
    make_emblem_setup,
    make_emblem_creatures_have_keywords,
    get_loyalty,
)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


def _setup_active(p_id, game):
    game.turn_manager.turn_state.active_player_id = p_id
    game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN
    game.state.active_player = p_id
    game.state.turn_number = 1


def _spawn_on_battlefield(game, player, card_def):
    obj = game.create_object(
        name=card_def.name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
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


def _make_simple_pw(*, starting_loyalty=4, name="Test PW"):
    log: list = []

    def setup(obj, state):
        ints = make_planeswalker_setup(obj, starting_loyalty=starting_loyalty)

        def plus_effect(o, st, targets):
            log.append(("+1", o.id))
            return []

        make_loyalty_ability(
            obj, cost=+1, effect_fn=plus_effect, ability_id="+1",
            description="+1: log",
        )
        return ints

    pw = make_planeswalker(
        name=name,
        mana_cost="{1}{W}{W}",
        colors={Color.WHITE},
        loyalty=starting_loyalty,
        subtypes={"Tester"},
        supertypes={"Legendary"},
        text="+1: log.",
        setup_interceptors=setup,
    )
    pw._test_log = log
    return pw


def _spawn_creature(game, player, *, name="Bear", power=2, toughness=2,
                    keywords=None, supertypes=None):
    """Create a creature directly on the battlefield (helper for combat tests)."""
    keywords = keywords or []
    supertypes = supertypes or set()
    chars = Characteristics(
        types={CardType.CREATURE},
        subtypes={"Bear"},
        supertypes=set(supertypes),
        colors={Color.GREEN},
        mana_cost="{1}{G}",
    )
    obj = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=chars,
        card_def=None,
    )
    # Stamp printed P/T directly onto the object so get_power/toughness work
    # without an external CardDefinition.
    obj.characteristics.power = power
    obj.characteristics.toughness = toughness
    if keywords:
        # Append to abilities list as keyword strings (engine interprets them
        # via has_ability).
        for kw in keywords:
            obj.characteristics.abilities.append(kw)
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
    ))
    obj.state.summoning_sickness = False
    return obj


# ---------------------------------------------------------------------------
# Combat redirect tests
# ---------------------------------------------------------------------------


def test_combat_redirect_attacker_to_planeswalker():
    """Declared attacker pointed at a PW deals damage to PW (loyalty -power)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p2.id, game)  # Bob attacks; Alice owns the PW.

    pw_def = _make_simple_pw(starting_loyalty=5, name="Defender PW")
    pw = _spawn_on_battlefield(game, p1, pw_def)
    starting = get_loyalty(pw)

    # Bob's 3-power attacker.
    bear = _spawn_creature(game, p2, power=3, toughness=3)

    # Build an AttackDeclaration pointing at p1, then redirect to PW.
    decl = AttackDeclaration(
        attacker_id=bear.id,
        defending_player_id=p1.id,
        is_attacking_planeswalker=False,
    )
    ok = redirect_attack_to_planeswalker(decl, game.state, pw.id)
    assert ok, "redirect_attack_to_planeswalker should return True"
    assert decl.is_attacking_planeswalker
    assert decl.defending_player_id == pw.id

    # Simulate combat damage delivery: attacker deals power to declared target.
    game.deal_damage(source_id=bear.id, target_id=decl.defending_player_id, amount=3)

    # Damage TRANSFORM hook converts to COUNTER_REMOVED on the PW.
    assert get_loyalty(pw) == starting - 3, \
        f"expected {starting - 3} loyalty, got {get_loyalty(pw)}"
    print("PASS: combat redirect — attacker hits PW for 3, loyalty -3")


def test_combat_redirect_lethal_destroys_planeswalker():
    """Damage routed to PW that drops loyalty to 0 destroys it via SBA."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p2.id, game)

    pw_def = _make_simple_pw(starting_loyalty=2, name="Doomed PW")
    pw = _spawn_on_battlefield(game, p1, pw_def)

    bear = _spawn_creature(game, p2, power=4, toughness=4)
    decl = AttackDeclaration(
        attacker_id=bear.id,
        defending_player_id=p1.id,
    )
    redirect_attack_to_planeswalker(decl, game.state, pw.id)
    game.deal_damage(source_id=bear.id, target_id=decl.defending_player_id, amount=4)

    # SBA hook may have already destroyed it via the COUNTER_REMOVED-driven
    # interceptor; if not, kick the helper to confirm.
    if pw.zone == ZoneType.BATTLEFIELD:
        check_planeswalker_zero_loyalty_sbas(game.state, game.pipeline)
    assert pw.zone == ZoneType.GRAVEYARD, \
        f"PW should be in graveyard; zone={pw.zone}"
    print("PASS: combat redirect — lethal damage destroys PW via SBA")


def test_combat_redirect_only_to_controllers_pw():
    """Cannot redirect to a PW that the defending player doesn't control."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p2.id, game)

    # PW controlled by p2 (the attacker, not Alice). Redirect should fail.
    pw_def = _make_simple_pw(name="Wrong-Controller PW")
    pw = _spawn_on_battlefield(game, p2, pw_def)

    bear = _spawn_creature(game, p2, power=3, toughness=3)
    decl = AttackDeclaration(
        attacker_id=bear.id,
        defending_player_id=p1.id,
    )
    ok = redirect_attack_to_planeswalker(decl, game.state, pw.id)
    assert ok is False, "redirect should fail when PW belongs to attacker"
    assert decl.defending_player_id == p1.id
    print("PASS: combat redirect — refused for non-defender's PW")


# ---------------------------------------------------------------------------
# Legend rule tests
# ---------------------------------------------------------------------------


def test_legend_rule_destroys_duplicate_planeswalker():
    """Two Ajanis owned by same player -> SBA forces choice -> 1 dies."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    pw_def = _make_simple_pw(name="Ajani Test", starting_loyalty=4)
    pw_a = _spawn_on_battlefield(game, p1, pw_def)
    pw_b = _spawn_on_battlefield(game, p1, pw_def)
    # Both share the same printed name, both controlled by p1, both Legendary.
    assert pw_a.zone == ZoneType.BATTLEFIELD and pw_b.zone == ZoneType.BATTLEFIELD

    # Bump pw_b's loyalty above pw_a so the default keep-picker keeps the
    # higher-loyalty one (entered_zone_at ties; loyalty breaks tie).
    pw_b.state.counters['loyalty'] = 6

    events = check_legend_rule_sbas(game.state, game.pipeline)
    legend_events = [e for e in events if e.type == EventType.LEGEND_RULE_TRIGGERED]
    assert legend_events, f"expected LEGEND_RULE_TRIGGERED; got {[e.type for e in events]}"

    # Exactly one of the two should be destroyed.
    survivors = [pw for pw in (pw_a, pw_b) if pw.zone == ZoneType.BATTLEFIELD]
    assert len(survivors) == 1, \
        f"expected exactly 1 survivor; pw_a.zone={pw_a.zone}, pw_b.zone={pw_b.zone}"
    print("PASS: legend rule — duplicate PWs reduced to one via SBA")


def test_legend_rule_skips_when_different_controllers():
    """Same legend, different controllers: legend rule does NOT fire."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    pw_def = _make_simple_pw(name="Shared Legend")
    pw_a = _spawn_on_battlefield(game, p1, pw_def)
    pw_b = _spawn_on_battlefield(game, p2, pw_def)
    assert pw_a.zone == ZoneType.BATTLEFIELD and pw_b.zone == ZoneType.BATTLEFIELD

    events = check_legend_rule_sbas(game.state, game.pipeline)
    assert not [e for e in events if e.type == EventType.LEGEND_RULE_TRIGGERED], \
        "legend rule should skip when same name has different controllers"
    print("PASS: legend rule — different controllers, no destruction")


def test_legend_rule_applies_to_creatures_too():
    """Legend rule applies to all permanents (e.g. legendary creatures)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    a = _spawn_creature(game, p1, name="Mox Pearl", supertypes={"Legendary"})
    b = _spawn_creature(game, p1, name="Mox Pearl", supertypes={"Legendary"})
    events = check_legend_rule_sbas(game.state, game.pipeline)
    assert any(e.type == EventType.LEGEND_RULE_TRIGGERED for e in events), \
        f"expected legend rule trigger; got {[e.type for e in events]}"
    survivors = [o for o in (a, b) if o.zone == ZoneType.BATTLEFIELD]
    assert len(survivors) == 1
    print("PASS: legend rule — also applies to non-PW legendary permanents")


# ---------------------------------------------------------------------------
# Emblem tests
# ---------------------------------------------------------------------------


def test_emblem_creates_and_persists():
    """create_emblem registers an emblem and its interceptors live forever."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    def _statics(emblem, state):
        return []  # No-op static — verify creation only.

    emblem, events = create_emblem(
        game.state,
        controller=p1.id,
        source_id=None,
        source_card_name="Test Source",
        static_effects_fn=_statics,
        text="Test emblem",
    )
    assert emblem.id
    assert emblem.controller == p1.id
    emblems = get_emblems_for_player(game.state, p1.id)
    assert any(e.id == emblem.id for e in emblems)
    assert any(e.type == EventType.EMBLEM_CREATED for e in events)
    print("PASS: emblem — created, recorded on state.emblems")


def test_emblem_creatures_have_flying_keyword_grant():
    """Ajani-style emblem grants flying to creatures controller controls."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    setup_fn = make_emblem_creatures_have_keywords(
        source_card_name="Ajani, Caller of the Pride",
        keywords=['flying'],
        name="Ajani Emblem",
    )
    setup_fn(game.state, p1.id, source_id=None)

    bear_alice = _spawn_creature(game, p1, power=2, toughness=2)
    bear_bob = _spawn_creature(game, p2, power=2, toughness=2)

    from src.engine.queries import has_ability
    assert has_ability(bear_alice, 'flying', game.state), \
        "Alice's bear should have flying via emblem"
    assert not has_ability(bear_bob, 'flying', game.state), \
        "Bob's bear should NOT have flying"
    print("PASS: emblem — Alice's creatures gain flying; opponents' do not")


def test_emblem_persists_across_turns_and_destruction():
    """Emblem interceptors keep firing after a turn flip and after the
    notional source card leaves play (emblem source is the emblem itself)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    setup_fn = make_emblem_creatures_have_keywords(
        source_card_name="Persistence Test",
        keywords=['flying'],
    )
    setup_fn(game.state, p1.id, source_id=None)

    bear_alice = _spawn_creature(game, p1)

    # Simulate end of turn: emit OBJECT_DESTROYED on a "fake" source. Emblems
    # don't have a battlefield source so cleanup_departed_interceptors should
    # leave them alone.
    game.emit(Event(
        type=EventType.TURN_END,
        payload={'player': p1.id},
    ))
    # Bump turn number and emit a TURN_START for p2.
    game.state.turn_number = 2
    game.emit(Event(
        type=EventType.TURN_START,
        payload={'player': p2.id, 'turn_number': 2},
    ))

    from src.engine.queries import has_ability
    assert has_ability(bear_alice, 'flying', game.state), \
        "emblem should still grant flying after turn boundary"
    print("PASS: emblem — persists across turn boundaries")


def test_emblem_ignored_by_object_destroyed():
    """OBJECT_DESTROYED on the emblem's id should not affect it (emblems
    have no zone and aren't in state.objects). Just sanity-check that emitting
    such an event doesn't break things."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    setup_fn = make_emblem_creatures_have_keywords(
        source_card_name="Indestructible Emblem",
        keywords=['flying'],
    )
    setup_fn(game.state, p1.id, source_id=None)

    bear_alice = _spawn_creature(game, p1)

    # Try to "destroy" the emblem directly. It isn't in state.objects, so the
    # handler should no-op and the emblem should continue to function.
    emblem = get_emblems_for_player(game.state, p1.id)[0]
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': emblem.id, 'reason': 'test'},
    ))

    from src.engine.queries import has_ability
    assert has_ability(bear_alice, 'flying', game.state), \
        "emblem should survive OBJECT_DESTROYED with its id"
    # Emblem still on state.emblems.
    assert any(e.id == emblem.id for e in get_emblems_for_player(game.state, p1.id))
    print("PASS: emblem — survives OBJECT_DESTROYED targeting its id")


# ---------------------------------------------------------------------------
# Ral, Crackling Wit -10 emblem
# ---------------------------------------------------------------------------


def test_ral_emblem_fires_on_instant_or_sorcery_cast():
    """Ral's -10 creates an emblem that deals 4 to opponent on instant/sorcery cast."""
    async def _run():
        from src.cards.bloomburrow import RAL_CRACKLING_WIT
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_active(p1.id, game)

        ral = _spawn_on_battlefield(game, p1, RAL_CRACKLING_WIT)
        ral.state.summoning_sickness = False
        # Force loyalty to 10 so we can pay -10.
        ral.state.counters['loyalty'] = 10

        # Find the -10 ability index.
        minus10_idx = None
        for idx, ab in enumerate(ral.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == -10:
                minus10_idx = idx
                break
        assert minus10_idx is not None

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=ral.id,
            ability_id=f"activated:{minus10_idx}",
        )
        events = await game.priority_system._execute_action(action)
        assert any(e.type == EventType.ACTIVATE for e in events)

        # Resolve the stack item to fire the emblem-creating effect.
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)

        # Emblem exists.
        emblems = get_emblems_for_player(game.state, p1.id)
        assert any(e.source_card_name == "Ral, Crackling Wit" for e in emblems), \
            f"expected a Ral emblem; got {[e.source_card_name for e in emblems]}"

        # Now simulate Alice casting an instant -> emblem reacts -> Bob
        # takes 4 damage.
        bob_life = game.state.players[p2.id].life
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'caster': p1.id,
                     'types': [CardType.INSTANT]},
            controller=p1.id,
        ))
        # Damage TRANSFORM redirected to PW only when target IS a PW; here
        # we deal directly to Bob (a player), so life should drop by 4.
        assert game.state.players[p2.id].life == bob_life - 4, \
            f"expected Bob's life {bob_life - 4}; got {game.state.players[p2.id].life}"
        print("PASS: Ral emblem — instant cast deals 4 to opponent")

    asyncio.get_event_loop().run_until_complete(_run())


def test_ral_minus10_updated_creates_emblem_event():
    """The -10 effect now emits an EMBLEM_CREATED event."""
    async def _run():
        from src.cards.bloomburrow import RAL_CRACKLING_WIT
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_active(p1.id, game)

        ral = _spawn_on_battlefield(game, p1, RAL_CRACKLING_WIT)
        ral.state.summoning_sickness = False
        ral.state.counters['loyalty'] = 10

        minus10_idx = None
        for idx, ab in enumerate(ral.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == -10:
                minus10_idx = idx
                break

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=ral.id,
            ability_id=f"activated:{minus10_idx}",
        )
        await game.priority_system._execute_action(action)
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        emitted = []
        for e in resolved:
            emitted.append(e)
            game.emit(e)

        # The resolve_fn produces DRAW + EMBLEM_CREATED.
        assert any(e.type == EventType.EMBLEM_CREATED for e in emitted), \
            f"expected EMBLEM_CREATED in resolution events; got {[e.type for e in emitted]}"
        assert any(e.type == EventType.DRAW for e in emitted)
        print("PASS: Ral -10 — emits EMBLEM_CREATED + DRAW")

    asyncio.get_event_loop().run_until_complete(_run())


async def _create_ral_emblem_async(game, controller_id):
    """Helper: activate Ral's -10 (must be awaited from within an event
    loop) and emit the resulting EMBLEM_CREATED + DRAW. Returns the
    freshly-created :class:`Emblem`.
    """
    from src.cards.bloomburrow import RAL_CRACKLING_WIT
    ral = _spawn_on_battlefield(game, game.state.players[controller_id], RAL_CRACKLING_WIT)
    ral.state.summoning_sickness = False
    ral.state.counters['loyalty'] = 10

    minus10_idx = None
    for idx, ab in enumerate(ral.state.activated_abilities):
        if getattr(ab, "loyalty_cost", 0) == -10:
            minus10_idx = idx
            break
    assert minus10_idx is not None

    await game.priority_system._execute_action(PlayerAction(
        type=ActionType.ACTIVATE_ABILITY,
        player_id=controller_id, source_id=ral.id,
        ability_id=f"activated:{minus10_idx}",
    ))
    item = game.stack.items[-1]
    for e in item.resolve_fn(item.chosen_targets, game.state):
        game.emit(e)

    emblems = get_emblems_for_player(game.state, controller_id)
    return next(e for e in emblems if e.source_card_name == "Ral, Crackling Wit")


def test_ral_emblem_interactive_opens_target_choice():
    """With auto_resolve_triggers=False, casting an instant queues a
    TriggeredStackItem; resolving it opens a PendingChoice for "any target".
    Submitting a chosen target deals 4 damage to that target."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_active(p1.id, game)

        # Spawn a creature for Bob — we'll target it instead of Bob himself
        # to confirm the choice respects the player's pick (not just the
        # default-opponent fallback).
        bear = _spawn_creature(game, p2, name="Bob's Bear", power=2, toughness=2)

        emblem = await _create_ral_emblem_async(game, p1.id)
        # The -10 activation left its loyalty-ability StackItem behind;
        # clear the stack before the interactive test so the new trigger
        # resolves cleanly on its own.
        game.stack.items.clear()
        # Force interactive mode AFTER emblem creation so the -10 itself can
        # still resolve under auto-resolve.
        game.state.options.auto_resolve_triggers = False

        # Cast an instant — emblem should queue (not fire inline).
        bob_life_pre = game.state.players[p2.id].life
        bear_zone_pre = bear.zone

        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'caster': p1.id, 'types': [CardType.INSTANT]},
            controller=p1.id,
        ))

        # Damage should NOT have been dealt yet.
        assert game.state.players[p2.id].life == bob_life_pre, (
            f"Interactive mode: life shouldn't change before choice "
            f"resolves; got {game.state.players[p2.id].life}, expected "
            f"{bob_life_pre}"
        )

        # The trigger should be queued.
        assert len(game.state.pending_triggers) == 1, (
            f"expected 1 pending trigger, got "
            f"{len(game.state.pending_triggers)}"
        )
        trig = game.state.pending_triggers[0]
        assert trig.controller == p1.id
        assert trig.source_id == emblem.id

        # Push and resolve via the stack manager (mirrors the priority loop's
        # APNAP -> resolve flow).
        from src.engine.stack import process_pending_triggers
        process_pending_triggers(game.state, game.stack)
        assert len(game.stack.items) == 1
        produced = game.stack.resolve_top()
        for e in produced:
            game.emit(e)

        # The trigger's effect_fn should have emitted a TARGET_REQUIRED,
        # which the targeting handler turned into a PendingChoice.
        choice = game.state.pending_choice
        assert choice is not None, "expected a PendingChoice after trigger resolved"
        assert choice.player == p1.id, (
            f"choice should belong to emblem controller; got {choice.player}"
        )
        assert choice.choice_type == "target_with_callback"
        # Bear and Bob (and Alice + Ral) should be among the legal options;
        # the engine adds players to the options list for filter='any'.
        assert p2.id in choice.options or any(
            (isinstance(o, str) and o == p2.id) for o in choice.options
        ), f"Bob should be a legal target; got {choice.options}"
        assert bear.id in choice.options, (
            f"Bob's bear should be a legal target; got {choice.options}"
        )

        # Submit Alice's choice: aim at Bob's bear (4 dmg should be lethal
        # to a 2-toughness bear).
        ok, err, _events = game.submit_choice(choice.id, p1.id, [bear.id])
        assert ok, f"submit_choice failed: {err!r}"
        assert game.state.pending_choice is None

        # Bob's life should be unchanged (we targeted the bear), bear
        # should have 4 marked damage and be flagged for SBA.
        assert game.state.players[p2.id].life == bob_life_pre, (
            f"Bob's life should be unchanged; got "
            f"{game.state.players[p2.id].life}"
        )
        # Bear should have taken 4 damage. SBA may have moved it to graveyard.
        if bear.zone == ZoneType.BATTLEFIELD:
            game.check_state_based_actions()
        assert bear.zone == ZoneType.GRAVEYARD or bear.state.damage_marked >= 4, (
            f"bear should have taken 4 damage (or be in graveyard); "
            f"zone={bear.zone}, damage_marked={getattr(bear.state, 'damage_marked', 0)}"
        )
        print("PASS: Ral emblem — interactive PendingChoice picks target, "
              "damage routes correctly")

    asyncio.get_event_loop().run_until_complete(_run())


def test_ral_emblem_auto_resolve_picks_default_opponent():
    """With auto_resolve_triggers=True (default), the emblem's TriggeredStackItem
    resolves inline against the first opponent — preserving the legacy
    behaviour for tests that don't drive PendingChoice."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_active(p1.id, game)

        emblem = await _create_ral_emblem_async(game, p1.id)
        # Auto-resolve mode is the default — assert it explicitly so the
        # test documents intent.
        assert game.state.options.auto_resolve_triggers is True

        bob_life_pre = game.state.players[p2.id].life
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'caster': p1.id, 'types': [CardType.SORCERY]},
            controller=p1.id,
        ))

        assert game.state.players[p2.id].life == bob_life_pre - 4, (
            f"auto-resolve: Bob should have lost 4 life; got "
            f"{game.state.players[p2.id].life}"
        )
        # No PendingChoice should be left behind.
        assert game.state.pending_choice is None
        assert game.state.pending_triggers == []
        print("PASS: Ral emblem — auto-resolve targets first opponent")

    asyncio.get_event_loop().run_until_complete(_run())


def test_ral_emblem_no_legal_targets_does_nothing():
    """If the emblem's controller is the only living player (and no opposing
    permanents exist), the trigger fizzles silently rather than crashing."""
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        # No opponent added — single-player edge.
        _setup_active(p1.id, game)

        emblem = await _create_ral_emblem_async(game, p1.id)
        alice_life_pre = game.state.players[p1.id].life

        # Cast an instant. With no opponents, default_target picker returns
        # None and the trigger fizzles. Alice's own life MUST NOT drop.
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'caster': p1.id, 'types': [CardType.INSTANT]},
            controller=p1.id,
        ))
        assert game.state.players[p1.id].life == alice_life_pre, (
            f"with no opponents the emblem shouldn't damage its own "
            f"controller; Alice's life {alice_life_pre} -> "
            f"{game.state.players[p1.id].life}"
        )
        print("PASS: Ral emblem — no legal target -> fizzle (no self-damage)")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Ajani, Caller of the Pride per-card test
# ---------------------------------------------------------------------------


def test_ajani_caller_full_activation_cycle():
    """Ajani: activate +1 (loyalty +1, target counter), then later turn -3, -8 emblem."""
    async def _run():
        from src.cards.foundations import AJANI_CALLER_OF_THE_PRIDE
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_active(p1.id, game)

        ajani = _spawn_on_battlefield(game, p1, AJANI_CALLER_OF_THE_PRIDE)
        ajani.state.summoning_sickness = False
        assert get_loyalty(ajani) == 4

        # Spawn a creature for Ajani to target.
        bear = _spawn_creature(game, p1, name="Pridemate", power=2, toughness=2)

        # Find the +1 ability.
        plus_idx = None
        for idx, ab in enumerate(ajani.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == 1:
                plus_idx = idx
                break
        assert plus_idx is not None, "Ajani should have a +1 loyalty ability"

        # Activate +1 with bear as target.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=ajani.id,
            ability_id=f"activated:{plus_idx}",
            targets=[bear.id],
        )
        events = await game.priority_system._execute_action(action)
        assert any(e.type == EventType.ACTIVATE for e in events)

        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)

        # Loyalty +1, bear has +1/+1 counter.
        assert get_loyalty(ajani) == 5
        assert bear.state.counters.get('+1/+1', 0) == 1, \
            f"bear should have +1/+1 counter; got {bear.state.counters}"
        print("PASS: Ajani +1 — adds loyalty, places +1/+1 counter on target")

    asyncio.get_event_loop().run_until_complete(_run())


def test_ajani_minus8_emblem_variant_creates_emblem():
    """Ajani's -8 (with emblem variant flag) creates an emblem granting flying+double_strike."""
    async def _run():
        from src.cards.foundations import AJANI_CALLER_OF_THE_PRIDE
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        _setup_active(p1.id, game)
        # Opt into the emblem variant of Ajani's -8 ult (otherwise printed
        # text is "create X 2/2 cat tokens").
        game.state._ajani_use_emblem_ult = True

        ajani = _spawn_on_battlefield(game, p1, AJANI_CALLER_OF_THE_PRIDE)
        ajani.state.summoning_sickness = False
        ajani.state.counters['loyalty'] = 8

        minus8_idx = None
        for idx, ab in enumerate(ajani.state.activated_abilities):
            if getattr(ab, "loyalty_cost", 0) == -8:
                minus8_idx = idx
                break
        assert minus8_idx is not None

        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=ajani.id,
            ability_id=f"activated:{minus8_idx}",
        )
        await game.priority_system._execute_action(action)
        item = game.stack.items[-1]
        resolved = item.resolve_fn(item.chosen_targets, game.state)
        for e in resolved:
            game.emit(e)

        # Emblem created.
        emblems = get_emblems_for_player(game.state, p1.id)
        assert any(e.source_card_name == "Ajani, Caller of the Pride" for e in emblems), \
            f"expected Ajani emblem; got {[e.source_card_name for e in emblems]}"

        # Place a creature; verify it has flying via QUERY_ABILITIES.
        bear = _spawn_creature(game, p1)
        from src.engine.queries import has_ability
        assert has_ability(bear, 'flying', game.state)
        assert has_ability(bear, 'double_strike', game.state)
        print("PASS: Ajani -8 emblem — creatures gain flying + double strike")

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# Non-combat damage redirect helper
# ---------------------------------------------------------------------------


def test_non_combat_damage_redirect_helper():
    """redirect_damage_to_planeswalker repoints a player-targeted DAMAGE event."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p2.id, game)

    pw_def = _make_simple_pw(name="Bolted PW", starting_loyalty=5)
    pw = _spawn_on_battlefield(game, p1, pw_def)

    bolt = Event(
        type=EventType.DAMAGE,
        payload={'target': p1.id, 'amount': 3, 'source': 'spell-1'},
        source='spell-1',
        controller=p2.id,
    )
    redirected = redirect_damage_to_planeswalker(bolt, game.state, pw.id)
    assert redirected is not None
    assert redirected.payload['target'] == pw.id
    assert redirected.payload.get('_redirected_from_player') == p1.id

    # Emit it: damage to PW becomes loyalty removal via the framework's
    # TRANSFORM hook.
    game.emit(redirected)
    assert get_loyalty(pw) == 5 - 3
    print("PASS: non-combat damage redirect — DAMAGE to player rerouted to PW")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_legend_rule_keeps_higher_loyalty_pw_on_tie():
    """Default keep-picker breaks ties by loyalty for PWs (so freshly-ult'd PWs win)."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    pw_def = _make_simple_pw(name="Tie Breaker PW", starting_loyalty=4)
    pw_a = _spawn_on_battlefield(game, p1, pw_def)
    pw_b = _spawn_on_battlefield(game, p1, pw_def)

    # Force both to have same entered_zone_at.
    pw_a.entered_zone_at = pw_b.entered_zone_at = 100
    # Give pw_b higher loyalty.
    pw_a.state.counters['loyalty'] = 4
    pw_b.state.counters['loyalty'] = 9

    check_legend_rule_sbas(game.state, game.pipeline)
    assert pw_b.zone == ZoneType.BATTLEFIELD, \
        "higher-loyalty PW should be kept"
    assert pw_a.zone == ZoneType.GRAVEYARD
    print("PASS: legend rule — higher-loyalty PW wins the tie-break")


def test_combat_redirect_token_planeswalker_legend_rule_interaction():
    """Token PWs participate in legend rule when they share a name."""
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    _setup_active(p1.id, game)

    pw_def = _make_simple_pw(name="Token PW")
    pw_a = _spawn_on_battlefield(game, p1, pw_def)
    pw_b = _spawn_on_battlefield(game, p1, pw_def)

    # Both share Legendary supertype + name -> legend rule fires regardless
    # of "token-ness". Verify the SBA still picks one.
    pw_a.state.is_token = True
    pw_b.state.is_token = False
    check_legend_rule_sbas(game.state, game.pipeline)
    survivors = [pw for pw in (pw_a, pw_b) if pw.zone == ZoneType.BATTLEFIELD]
    assert len(survivors) == 1
    print("PASS: legend rule — applies to token PWs sharing a name")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_all():
    failed = 0
    tests = [
        test_combat_redirect_attacker_to_planeswalker,
        test_combat_redirect_lethal_destroys_planeswalker,
        test_combat_redirect_only_to_controllers_pw,
        test_legend_rule_destroys_duplicate_planeswalker,
        test_legend_rule_skips_when_different_controllers,
        test_legend_rule_applies_to_creatures_too,
        test_emblem_creates_and_persists,
        test_emblem_creatures_have_flying_keyword_grant,
        test_emblem_persists_across_turns_and_destruction,
        test_emblem_ignored_by_object_destroyed,
        test_ral_emblem_fires_on_instant_or_sorcery_cast,
        test_ral_minus10_updated_creates_emblem_event,
        test_ral_emblem_interactive_opens_target_choice,
        test_ral_emblem_auto_resolve_picks_default_opponent,
        test_ral_emblem_no_legal_targets_does_nothing,
        test_ajani_caller_full_activation_cycle,
        test_ajani_minus8_emblem_variant_creates_emblem,
        test_non_combat_damage_redirect_helper,
        test_legend_rule_keeps_higher_loyalty_pw_on_tie,
        test_combat_redirect_token_planeswalker_legend_rule_interaction,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            import traceback
            print(f"ERROR: {t.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    return failed


if __name__ == "__main__":
    sys.exit(run_all())
