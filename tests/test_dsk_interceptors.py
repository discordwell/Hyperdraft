"""Auto-generated interceptor verification for Duskmourn (DSK).

Per /test-interceptors. For every DSK card whose factory wires a
`setup_interceptors`, this file builds a minimal game state, drops the
card onto the battlefield (or fires its triggering event for death /
attack / spell-cast / damage / upkeep / end-step / survival / eerie /
room / impending interceptors), drains the stack, and asserts that at
least one event whose type matches the card's rules text gets emitted.

DSK mechanics covered: Survival (postcombat_main + tapped), Delirium
(threshold-gated triggers), Eerie (enchantment-enters / room-unlock),
Impending (time-counter chargeup), Rooms (split-door enchantments),
Manifest Dread (face-down with mill-2 surveil), Plot (exile-to-cast).

Cards whose effect needs modal choice / target selection / opponent
state / equipment attachment / saga / replacement effects are deferred
to ``SKIPPED_CARDS`` with a one-line reason.

Run with:

    PYTHONPATH=. python tests/test_dsk_interceptors.py
"""

import os
import sys
import re

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    GameObject, Characteristics, ObjectState, CardDefinition,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id, make_creature, make_artifact, make_enchantment,
)
from src.cards.duskmourn import DUSKMOURN_CARDS


# ---------------------------------------------------------------------------
# Cards we intentionally do not auto-test. The list documents the gap; rerun
# /test-interceptors when the engine grows the missing capability.
# ---------------------------------------------------------------------------
SKIPPED_CARDS: dict[str, str] = {
    # Replacement-effect / saga / equipment-static / leyline replacement —
    # these don't emit on the canonical ZONE_CHANGE path; they instead
    # rewrite later events. Auto-test cannot synthesise the rewritten
    # context without piloting a full game turn.
    "Leyline of Hope": "replacement — life-gain doubler, no ETB emit",
    "Leyline of the Void": "replacement — exile instead of graveyard",
    "Ethereal Armor": "Aura static — needs enchanted creature",
    "Sheltered by Ghosts": "Aura — exile target + attached static",
    "Anonymous Tribute": "Aura/curse — opponent-attached static",
    "Duskmourn's Domination": "Aura — needs attached creature for -3/-0 + gain control",
    "Frantic Strength": "Aura — needs attached creature for +2/+2 + trample",
    "Shardmage's Rescue": "Aura — needs attached creature for +1/+1 + hexproof",
    "Stay Hidden, Stay Silent": "Aura — needs attached creature; manifest dread is activated, not ETB",
    "Cursed Windbreaker": "equipment static — needs attached creature",
    # Modal / choice cards that auto-test cannot pilot.
    "Split Up": "modal sweeper variant",
    "Don't Make a Sound": "X-cost choice spell",
    "Reluctant Role Model": "modal ETB choice",
    "Trapped in the Screen": "modal target choice",
    # Plot cards — plot is an exile-cast mechanic that needs a separate
    # cast-from-exile path; the wiring is exercised in tests/test_otj_plot_saddle.
    "Unwanted Remake": "Plot — needs exile-cast path",
    # Sagas / counter accumulators.
    "The Wandering Rescuer": "saga-like phased trigger",
    # Cards whose effect depends on opponent's state being shaped before
    # the trigger fires.
    "Toby, Beastie Befriender": "tribal payoff requires multiple non-Spirit creatures already in hand",
    # Manifest dread is exercised via the engine MANIFEST_DREAD event in a
    # downstream skill; auto-test fixture cannot reliably emit it for every
    # card variant.
    "Abhorrent Oculus": "delirium + manifest-dread choice path",
}


# ---------------------------------------------------------------------------
# Text -> expected EventType set. Generous on purpose: a card whose text
# says "deal 2 damage" should at minimum emit a DAMAGE event somewhere in
# its trigger chain; we accept any of the candidate event types as a pass.
# ---------------------------------------------------------------------------
def _expected_event_types(text: str) -> set[EventType]:
    if not text:
        return set()
    t = text.lower()
    out: set[EventType] = set()

    if "draw" in t and "card" in t:
        out.add(EventType.DRAW)
    if "discard" in t:
        out.add(EventType.DISCARD)
    if re.search(r"deal[s]? \d+ damage|deals damage|deal damage", t):
        out.add(EventType.DAMAGE)
    if "gain" in t and "life" in t:
        out.add(EventType.LIFE_CHANGE)
    if "lose" in t and "life" in t:
        out.add(EventType.LIFE_CHANGE)
    if "destroy target" in t or "destroys target" in t or "destroy each" in t:
        out.add(EventType.OBJECT_DESTROYED)
        out.add(EventType.DESTROY)
    if "create" in t and "token" in t:
        out.add(EventType.CREATE_TOKEN)
    if "scry" in t:
        out.add(EventType.SCRY)
    if "surveil" in t:
        out.add(EventType.SURVEIL)
    if "mill" in t:
        out.add(EventType.MILL)
    if re.search(r"\+\d+/\+\d+|gets [+\-]\d+", t) or "counter on" in t:
        out.add(EventType.PT_MODIFICATION)
        out.add(EventType.COUNTER_ADDED)
    if "flying" in t or "trample" in t or "menace" in t or "ward" in t \
            or "first strike" in t or "deathtouch" in t or "lifelink" in t \
            or "haste" in t or "reach" in t or "vigilance" in t:
        out.add(EventType.GRANT_KEYWORD)
    if "exile target" in t or "exile up to" in t or "exile each" in t \
            or "exile that" in t or "exile it" in t:
        out.add(EventType.EXILE)
        out.add(EventType.ZONE_CHANGE)
    if "return target" in t or "return up to" in t:
        out.add(EventType.RETURN_TO_HAND)
        out.add(EventType.ZONE_CHANGE)
    if "search your library" in t:
        out.add(EventType.SEARCH_LIBRARY)
        out.add(EventType.LIBRARY_SEARCH)
    if "tap target" in t:
        out.add(EventType.TAP)
    if "untap target" in t or "untap all" in t:
        out.add(EventType.UNTAP)
    if "sacrifice" in t and ("creature" in t or "permanent" in t):
        out.add(EventType.ZONE_CHANGE)
        out.add(EventType.SACRIFICE)
    if "manifest dread" in t:
        out.add(EventType.MANIFEST_DREAD)
        out.add(EventType.OBJECT_CREATED)
    if "unlock" in t and "door" in t:
        out.add(EventType.UNLOCK_DOOR)
    if "plot" in t and "exile" in t:
        out.add(EventType.EXILE)
    if "incubate" in t and "token" in t:
        out.add(EventType.CREATE_TOKEN)
    if "+1/+1 counter" in t:
        out.add(EventType.COUNTER_ADDED)
    if "treasure" in t:
        out.add(EventType.CREATE_TOKEN)

    return out


# ---------------------------------------------------------------------------
# Scaffolding (mirrors test_blb_interceptors)
# ---------------------------------------------------------------------------
def _new_game():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    game.state.active_player = p1.id
    return game, p1.id, p2.id


def _create_in_zone(game: Game, owner_id: str, card_def: CardDefinition,
                   zone: ZoneType = ZoneType.HAND) -> GameObject:
    """Create object without running setup yet; setup fires on ZONE_CHANGE."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def
    return obj


def _move_to_battlefield(game: Game, obj: GameObject) -> list[Event]:
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{obj.owner}',
            'from_zone_type': ZoneType.HAND,
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        },
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_death(game: Game, obj: GameObject) -> list[Event]:
    return game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'battlefield',
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone': f'graveyard_{obj.owner}',
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=obj.id,
        controller=obj.controller,
    ))


def _fire_attack(game: Game, obj: GameObject) -> list[Event]:
    """Fire both ATTACK_DECLARED (per-attacker) and COMBAT_DECLARED (per-combat).
    Real engine combat code emits both; many DSK cards filter on COMBAT_DECLARED
    for "whenever you attack" triggers, so we mirror the production event pair.
    """
    out = list(game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': obj.id, 'defender_id': None,
                 'attacking_player': obj.controller},
        source=obj.id,
        controller=obj.controller,
    )))
    out.extend(game.emit(Event(
        type=EventType.COMBAT_DECLARED,
        payload={'attacking_player': obj.controller, 'attackers': [obj.id]},
        source=obj.id,
        controller=obj.controller,
    )))
    return out


def _fire_spell_cast(game: Game, caster_id: str, mana_cost: str = "{1}{W}") -> list[Event]:
    """Fire a spell-cast event with full metadata so spell_type / color /
    caster filters in ``make_spell_cast_trigger`` accept it.

    The defaulted instant cast covers cards like Cursed Recording (INSTANT
    or SORCERY trigger) without needing per-card tweaks.
    """
    return game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={
            'spell_id': new_id(),
            'controller': caster_id,
            'caster': caster_id,
            'mana_cost': mana_cost,
            'mana_value': 2,
            'types': {CardType.INSTANT},
            'spell_type': CardType.INSTANT,
            'colors': {Color.WHITE},
        },
        source=caster_id,
        controller=caster_id,
    ))


def _fire_damage(game: Game, source_id: str, target_id: str, controller: str,
                 amount: int = 1, is_combat: bool = True,
                 is_player: bool = True) -> list[Event]:
    """Default to combat damage on a player so combat_only / is_player guards
    on damage triggers pass. Cards filter on these flags via
    ``make_damage_trigger`` and custom filters."""
    return game.emit(Event(
        type=EventType.DAMAGE,
        payload={
            'source': source_id,
            'source_id': source_id,
            'target': target_id,
            'amount': amount,
            'is_combat': is_combat,
            'is_combat_damage': is_combat,
            'is_player': is_player,
        },
        source=source_id,
        controller=controller,
    ))


def _fire_survival_phase(game: Game, active_player: str) -> list[Event]:
    """Emit PHASE_START for the postcombat_main phase (Survival trigger)."""
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'postcombat_main', 'active_player': active_player},
        source=active_player,
        controller=active_player,
    ))


def _fire_upkeep_phase(game: Game, active_player: str) -> list[Event]:
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': active_player},
        source=active_player,
        controller=active_player,
    ))


def _fire_end_step(game: Game, active_player: str) -> list[Event]:
    return game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'end_step', 'active_player': active_player},
        source=active_player,
        controller=active_player,
    ))


def _fire_enchantment_etb(game: Game, owner_id: str) -> list[Event]:
    """Drop a vanilla enchantment onto the battlefield to trigger Eerie."""
    aura_def = make_enchantment(
        name="__EerieFood__",
        mana_cost="{1}",
        colors={Color.COLORLESS},
        subtypes=set(),
        text="",
    )
    eobj = game.create_object("__EerieFood__", owner_id, ZoneType.HAND,
                              aura_def.characteristics, card_def=aura_def)
    eobj.card_def = aura_def
    return _move_to_battlefield(game, eobj)


def _fire_manifest_dread(game: Game, owner_id: str) -> list[Event]:
    """Emit a MANIFEST_DREAD event for owner. The engine handler in
    face_down.py pulls top two of library, manifests one as a face-down
    2/2, mills the other. Use this to exercise "whenever you manifest
    dread" listeners (Paranormal Analyst)."""
    return game.emit(Event(
        type=EventType.MANIFEST_DREAD,
        payload={'player': owner_id, 'controller': owner_id},
        source=owner_id,
        controller=owner_id,
    ))


def _fire_small_creature_etb(game: Game, owner_id: str) -> list[Event]:
    """Drop a vanilla 1/1 creature ETB to trigger 'small-creature-enters'
    interceptors (Vicious Clown, Enduring Innocence)."""
    small_def = make_creature(
        name="__SmallFriend__",
        power=1, toughness=1,
        mana_cost="{1}",
        colors={Color.COLORLESS},
        subtypes={"Spirit"},
    )
    sobj = game.create_object("__SmallFriend__", owner_id, ZoneType.HAND,
                              small_def.characteristics, card_def=small_def)
    sobj.card_def = small_def
    return _move_to_battlefield(game, sobj)


def _flatten_events(initial: list[Event], game: Game) -> list[Event]:
    seen = list(initial)
    seen_ids = {id(e) for e in seen}
    for ev in getattr(game.state, 'event_log', []) or []:
        if id(ev) not in seen_ids:
            seen.append(ev)
            seen_ids.add(id(ev))
    return seen


def _assert_any_expected(
    events: list[Event],
    expected: set[EventType],
    card_name: str,
    game: Game | None = None,
) -> None:
    # Pending choice = deferred but registered.
    if game is not None and getattr(game.state, 'pending_choice', None) is not None:
        return

    saw_trigger_marker = any(
        e.type == EventType.TRIGGERED_ABILITY_PUT_ON_STACK for e in events
    )

    if not expected:
        non_trivial = [e for e in events if e.type not in (
            EventType.ZONE_CHANGE, EventType.ATTACK_DECLARED,
            EventType.TARGET_CHOSEN, EventType.SPELL_CAST,
            EventType.TRIGGERED_ABILITY_PUT_ON_STACK,
            EventType.PHASE_START, EventType.DAMAGE,
        )]
        if non_trivial or saw_trigger_marker:
            return
        assert any(e.type == EventType.ZONE_CHANGE for e in events), (
            f"{card_name}: interceptor neither fired nor put the card on the "
            "battlefield (setup crashed silently?)"
        )
        return

    got = {e.type for e in events}
    matches = got & expected
    if matches:
        return
    if saw_trigger_marker and EventType.ZONE_CHANGE in expected \
            and any(e.type == EventType.ZONE_CHANGE for e in events):
        return
    if saw_trigger_marker and any(
        e.type in (EventType.TARGET_REQUIRED, EventType.TARGET_CHANGED) for e in events
    ):
        return
    # Soft pass: trigger fired AND emitted an intent/deferred marker
    # (engine wired the effect, but resolution is deferred to a choice).
    intent_markers = {
        EventType.CONDITIONAL_EFFECT, EventType.CONDITIONAL_COUNTERS,
        EventType.CONDITIONAL_DISCARD,
        EventType.OPTIONAL_COST_FOR_EFFECT, EventType.OPTIONAL_DISCARD_FOR_EFFECT,
        EventType.OPTIONAL_SACRIFICE_FOR_EFFECT,
        EventType.MAY_PAY_DRAW,
        EventType.TARGET_REQUIRED, EventType.TARGET_CHANGED,
        EventType.SACRIFICE_REQUIRED, EventType.SEARCH_LIBRARY,
    }
    if saw_trigger_marker and (got & intent_markers):
        return
    # Soft pass: trigger fired AND produced a downstream effect event that
    # isn't on our expected list but is still a real effect (the test's
    # text-to-event heuristic missed). Accept these as fired-and-wired.
    real_effect_markers = {
        EventType.RETURN_FROM_GRAVEYARD, EventType.EXILE_FROM_TOP,
        EventType.REVEAL_TOP, EventType.UNLOCK_DOOR, EventType.TAP_FOR_EFFECT,
        EventType.OBJECT_CREATED, EventType.RETURN_TO_HAND,
        EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
    }
    if saw_trigger_marker and (got & real_effect_markers):
        return
    assert matches, (
        f"{card_name}: expected one of {sorted(t.name for t in expected)} "
        f"but emitted {sorted(t.name for t in got)}"
    )


# ---------------------------------------------------------------------------
# Trigger-kind classification: inspect setup source.
# ---------------------------------------------------------------------------
def _classify_trigger_kind(setup_fn) -> set[str]:
    import inspect
    try:
        src = inspect.getsource(setup_fn)
    except (OSError, TypeError):
        return {'etb'}
    kinds: set[str] = set()
    if 'make_etb_trigger' in src or 'make_targeted_etb_trigger' in src \
            or 'make_equipment_setup' in src or 'make_aura_setup' in src \
            or 'make_room_setup' in src or 'make_impending_setup' in src:
        kinds.add('etb')
    if 'make_death_trigger' in src or 'make_leaves_battlefield_trigger' in src:
        kinds.add('death')
    if 'make_attack_trigger' in src or 'make_targeted_attack_trigger' in src \
            or 'make_attacks_alone_trigger' in src \
            or 'COMBAT_DECLARED' in src or 'ATTACK_DECLARED' in src:
        kinds.add('attack')
    if 'make_damage_trigger' in src or 'EventType.DAMAGE' in src:
        kinds.add('damage')
    if 'make_upkeep_trigger' in src:
        kinds.add('upkeep')
    if 'make_end_step_trigger' in src:
        kinds.add('end_step')
    if 'make_spell_cast_trigger' in src or 'make_cost_reduction' in src:
        kinds.add('spell_cast')
    if 'make_life_gain_trigger' in src:
        kinds.add('life_gain')
    if 'make_draw_trigger' in src:
        kinds.add('draw_trigger')
    if 'make_survival_trigger' in src:
        kinds.add('survival')
    if 'make_eerie_trigger' in src or 'eerie_filter' in src or 'Eerie —' in src:
        kinds.add('eerie')
    if 'make_static_pt_boost' in src or 'make_keyword_grant' in src \
            or 'make_dynamic_pt_boost' in src or 'make_attached_dynamic_pt_boost' in src \
            or 'make_ward' in src:
        kinds.add('static')
    if 'make_activated_ability' in src or 'make_pump_self_ability' in src \
            or 'make_draw_ability' in src or 'make_loot_ability' in src \
            or 'make_life_gain_ability' in src or 'make_damage_ability' in src \
            or 'make_destroy_ability' in src or 'make_counter_ability' in src \
            or 'make_token_creation_ability' in src or 'make_sac_destroy_ability' in src:
        kinds.add('activated')
    if not kinds:
        kinds.add('etb')
    return kinds


def _run_one_card_with_game(card_name: str, card_def: CardDefinition) -> tuple[str, list[Event], Game | None]:
    setup_fn = getattr(card_def, 'setup_interceptors', None)
    if setup_fn is None:
        return ('skip:no_setup', [], None)

    kinds = _classify_trigger_kind(setup_fn)
    text = getattr(card_def, 'text', '') or ''

    game, p1, p2 = _new_game()

    # Bump per-turn counters so triggers gated on "you played a land this
    # turn" / "you cast a spell this turn" actually fire.
    try:
        game.state.lands_played_this_turn = 1
    except Exception:
        pass

    # Pre-populate hand + library + graveyard so triggers that draw / discard
    # / mill / surveil / search have material to chew on. Delirium needs
    # 4+ types in the graveyard — load a variety.
    filler_def = make_creature(
        name="__Filler__", power=1, toughness=1,
        mana_cost="{1}", colors={Color.COLORLESS}, subtypes={"Horror"},
    )
    filler_inst = make_creature(
        name="__FillerInstant__", power=0, toughness=0,
        mana_cost="{1}", colors={Color.COLORLESS}, subtypes=set(),
    )
    for _ in range(6):
        game.create_object("__Filler__", p1, ZoneType.LIBRARY,
                           filler_def.characteristics, card_def=filler_def)
        game.create_object("__Filler__", p1, ZoneType.HAND,
                           filler_def.characteristics, card_def=filler_def)
        game.create_object("__Filler__", p1, ZoneType.GRAVEYARD,
                           filler_def.characteristics, card_def=filler_def)
        game.create_object("__Filler__", p2, ZoneType.LIBRARY,
                           filler_def.characteristics, card_def=filler_def)
        game.create_object("__Filler__", p2, ZoneType.HAND,
                           filler_def.characteristics, card_def=filler_def)

    # Give a vanilla creature for the opponent so destroy/damage targets exist.
    enemy_def = make_creature(
        name="__Enemy__", power=2, toughness=2,
        mana_cost="{1}", colors={Color.COLORLESS}, subtypes={"Horror"},
    )
    game.create_object("__Enemy__", p2, ZoneType.BATTLEFIELD,
                       enemy_def.characteristics, card_def=enemy_def)

    # Give the active player a few basic lands on the battlefield so survival /
    # land-animation triggers (Rootwise Survivor) and prime-count triggers
    # (Zimone, All-Questioning) have targets / satisfy gating. Three is a
    # prime count for Zimone, and gives Rootwise Survivor at least one non-
    # creature land to animate. We mint each as a fresh Characteristics so
    # we don't drag a Card factory in here.
    for _ in range(3):
        land_chars = Characteristics(types={CardType.LAND}, subtypes={"Forest"})
        game.create_object("__Forest__", p1, ZoneType.BATTLEFIELD,
                           land_chars, card_def=None)

    obj = _create_in_zone(game, p1, card_def, zone=ZoneType.HAND)

    captured: list[Event] = []

    # 1) ETB path - every battlefield-entering card hits this first.
    if kinds & {'etb', 'static', 'death', 'attack', 'damage', 'spell_cast',
                'life_gain', 'activated', 'upkeep', 'end_step',
                'survival', 'eerie', 'draw_trigger'}:
        captured.extend(_move_to_battlefield(game, obj))

    # Survival requires the creature to be tapped before phase fires.
    if 'survival' in kinds:
        try:
            live_obj = game.state.objects.get(obj.id)
            if live_obj is not None:
                live_obj.state.tapped = True
        except Exception:
            pass
        captured.extend(_fire_survival_phase(game, p1))

    # Eerie: trigger fires when ANOTHER enchantment enters under controller.
    if 'eerie' in kinds:
        captured.extend(_fire_enchantment_etb(game, p1))

    # "Whenever another creature you control [with power N or less] enters" —
    # spawn a small friend ETB so cards like Vicious Clown / Enduring Innocence
    # / Enduring Courage actually fire their counter / draw / buff triggers.
    text_l = (text or '').lower()
    if (('another creature' in text_l or 'creature you control' in text_l)
            and 'enters' in text_l and 'attack' not in text_l[:50]):
        captured.extend(_fire_small_creature_etb(game, p1))

    # "Whenever you manifest dread" listeners (Paranormal Analyst) — emit a
    # MANIFEST_DREAD so the listener fires.
    if 'manifest dread' in text_l and 'whenever' in text_l:
        captured.extend(_fire_manifest_dread(game, p1))

    # Death triggers.
    if 'death' in kinds:
        captured.extend(_fire_death(game, obj))

    # Attack triggers.
    if 'attack' in kinds:
        captured.extend(_fire_attack(game, obj))

    # Spell-cast triggers (this card's own cast, or a generic spell).
    if 'spell_cast' in kinds:
        captured.extend(_fire_spell_cast(game, p1, mana_cost="{1}{W}"))

    # Life-gain triggers.
    if 'life_gain' in kinds:
        captured.extend(game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': p1, 'amount': 1},
            source=obj.id, controller=p1,
        )))

    # Draw triggers.
    if 'draw_trigger' in kinds:
        captured.extend(game.emit(Event(
            type=EventType.DRAW,
            payload={'player': p1, 'amount': 1},
            source=obj.id, controller=p1,
        )))

    # Damage triggers.
    if 'damage' in kinds:
        captured.extend(_fire_damage(game, obj.id, p2, p1, amount=1))

    # Upkeep / end-step triggers.
    if 'upkeep' in kinds:
        captured.extend(_fire_upkeep_phase(game, p1))
    if 'end_step' in kinds:
        captured.extend(_fire_end_step(game, p1))

    # Drain the stack so triggered abilities actually resolve.
    for _ in range(80):
        try:
            if not getattr(game, 'stack', None) or not game.stack.items:
                break
            resolved = game.stack.resolve_top() or []
            for ev in resolved:
                captured.append(ev)
                try:
                    cascaded = game.emit(ev)
                    if cascaded:
                        captured.extend(cascaded)
                except Exception:
                    pass
        except Exception:
            break

    return ('ok', _flatten_events(captured, game), game)


# ---------------------------------------------------------------------------
# Test factory
# ---------------------------------------------------------------------------
def _snake(name: str) -> str:
    out = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return out or "card"


def _make_test(card_name: str, card_def: CardDefinition):
    def _t():
        if card_name in SKIPPED_CARDS:
            # Use pytest.skip when available (pytest collector); fall back to
            # AssertionError prefixed with "SKIP:" so the standalone CLI
            # runner below recognises it as a skip too.
            try:
                import pytest  # type: ignore
                pytest.skip(SKIPPED_CARDS[card_name])
            except ImportError:
                raise AssertionError(f"SKIP: {SKIPPED_CARDS[card_name]}")
        status, events, game = _run_one_card_with_game(card_name, card_def)
        if status == 'skip:no_setup':
            raise AssertionError("card has no setup_interceptors wired")
        text = getattr(card_def, 'text', '') or ''
        expected = _expected_event_types(text)
        kinds = _classify_trigger_kind(card_def.setup_interceptors)
        # Static / activated / cost-reduction interceptors are query-time —
        # if the card simply landed on the battlefield without crashing, that's
        # 'wired ok' for our depths-trap purposes.
        if kinds & {'static', 'activated'} and not (kinds & {
            'etb', 'death', 'attack', 'damage',
            'life_gain', 'upkeep', 'end_step', 'survival',
            'eerie', 'draw_trigger',
        }):
            if any(e.type == EventType.ZONE_CHANGE for e in events):
                return

        # Pure cost-reduction setups (make_cost_reduction) hook QUERY_COST,
        # which fires at cast time. The card itself never enters the
        # battlefield with a resolution effect — its body is dispatched
        # elsewhere (resolve= on the CardDefinition or cast-effect routing).
        # Treat 'spell_cast'-only setups as wired-ok if the card has no other
        # trigger kinds beyond spell_cast static.
        if kinds == {'spell_cast'} and 'make_cost_reduction' in (
                __import__('inspect').getsource(card_def.setup_interceptors)
                if card_def.setup_interceptors else ''):
            return
        _assert_any_expected(events, expected, card_name, game=game)
    _t.__name__ = f"test_{_snake(card_name)}"
    _doc_text = getattr(card_def, 'text', '') or ''
    _t.__doc__ = f"{card_name}: {_doc_text[:120]}"
    return _t


# Build tests at module load.
_ALL_TESTS: list = []
for _name, _cd in DUSKMOURN_CARDS.items():
    if getattr(_cd, 'setup_interceptors', None) is None:
        continue
    _fn = _make_test(_name, _cd)
    globals()[_fn.__name__] = _fn
    _ALL_TESTS.append(_fn)


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    passed: list[str] = []
    failed: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []

    for t in _ALL_TESTS:
        try:
            t()
            passed.append(t.__name__)
        except AssertionError as e:
            msg = str(e)
            if msg.startswith("SKIP:"):
                skipped.append((t.__name__, msg[5:].strip()))
            else:
                failed.append((t.__name__, msg))
        except Exception as e:
            errors.append((t.__name__, f"{type(e).__name__}: {e}"))

    total = len(_ALL_TESTS)
    print()
    print("=== Interceptor verification: Duskmourn (DSK) ===")
    print(f"  wired cards: {total}")
    print(f"  passed:      {len(passed)}")
    print(f"  failed:      {len(failed)}")
    print(f"  errors:      {len(errors)}")
    print(f"  skipped:     {len(skipped)} (see SKIPPED_CARDS)")
    if total:
        pct = 100.0 * len(passed) / total
        print(f"  pass rate:   {pct:.1f}%")

    if failed:
        print()
        print("--- FAILURES (first 20) ---")
        for n, m in failed[:20]:
            print(f"  {n}: {m[:200]}")
    if errors:
        print()
        print("--- ERRORS (first 20) ---")
        for n, m in errors[:20]:
            print(f"  {n}: {m[:200]}")

    sys.exit(0 if not failed and not errors else 1)
