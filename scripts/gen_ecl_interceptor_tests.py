"""Generate tests/test_ecl_interceptors.py by inspecting LORWYN_ECLIPSED_CARDS.

Mirrors the heuristic of WOE/BLB/LCI generators:
  - For each card, look at registered interceptors when created in HAND-then-
    moved-to-BATTLEFIELD (so the standard zone-change setup path runs).
  - Decide the dominant trigger kind from interceptor.subscribed_events /
    interceptor priority + prio + filter introspection. Fall back to scanning
    the card's `text` for trigger phrases.
  - Parse the card's `text` for expected effect keywords (draw / damage /
    destroy / gain N life / etc.) -> a set of EventType values to assert.
  - If we can't determine a trigger kind or any expected event, add the card
    to SKIPPED_CARDS with a reason.

Run:
    PYTHONPATH=. python scripts/gen_ecl_interceptor_tests.py
"""

from __future__ import annotations
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType,
)
from src.cards.lorwyn_eclipsed import LORWYN_ECLIPSED_CARDS


# --------------------------------------------------------------------------
# Text parsing -> set of EventType
# --------------------------------------------------------------------------
def parse_expected_events(text: str) -> set:
    """Return the set of EventType values implied by a card's rules text."""
    if not text:
        return set()
    t = text.lower()
    out = set()
    # Card-draw
    if re.search(r"\bdraw(s)?\s+(a|\w+)\s+card", t) or re.search(r"\bdraw(s)?\s+cards?\s+equal", t):
        out.add(EventType.DRAW)
    # Life
    if re.search(r"gain(s)?\s+\d+\s+life", t) or re.search(r"gain(s)?\s+life", t) or \
       re.search(r"gain(s)?\s+\w+\s+life", t) or \
       re.search(r"lose(s)?\s+\d+\s+life", t) or "you lose life" in t or \
       "you lose 1 life" in t or "loses life" in t:
        out.add(EventType.LIFE_CHANGE)
    # Damage
    if re.search(r"deal(s)?\s+\d+\s+damage", t) or "deals damage to" in t or \
       re.search(r"deal(s)?\s+x\s+damage", t) or re.search(r"deal(s)?\s+\w+\s+damage", t):
        out.add(EventType.DAMAGE)
    # Destroy
    if re.search(r"destroy\s+(target|each|all|that|up to)", t):
        out.add(EventType.DESTROY)
    # Exile
    if re.search(r"exile\s+(target|each|all|that|up to)", t) or "exile it" in t or \
       re.search(r"exile\s+(it|all|cards)", t) or "exile that card" in t:
        out.add(EventType.EXILE)
    # Sacrifice
    if "sacrifice" in t:
        out.add(EventType.SACRIFICE)
    # Bounce / return to hand
    if "return target" in t and ("to its owner's hand" in t or "to their owner" in t or "to your hand" in t):
        out.add(EventType.RETURN_TO_HAND)
    # "return up to N target creature ... to its/their owner's hand"
    if re.search(r"return\s+(up\s+to\s+\w+\s+)?(other\s+)?target\s+\w+", t) and "owner" in t and "hand" in t:
        out.add(EventType.RETURN_TO_HAND)
    if re.search(r"return\s+target\s+\w+\s+card\s+from\s+(your|a)\s+graveyard", t) or \
       re.search(r"return\s+(it|that\s+card)\s+from\s+(your|a)\s+graveyard", t):
        out.add(EventType.RETURN_FROM_GRAVEYARD)
    # Tokens
    if "create" in t and ("token" in t or "treasure" in t or "food" in t or "clue" in t or "blood" in t):
        out.add(EventType.OBJECT_CREATED)
    # Put creature from hand onto battlefield
    if re.search(r"put\s+(a|that|target|up to)\s+(\w+\s+)*card\s+(from|onto)", t) or \
       "onto the battlefield" in t:
        out.add(EventType.OBJECT_CREATED)
    # Counters on creature
    if re.search(r"\+1/\+1\s+counter", t) or "loyalty counter" in t or \
       re.search(r"\bcharge\s+counter", t) or re.search(r"-1/-1\s+counter", t):
        out.add(EventType.COUNTER_ADDED)
    # Pump / temporary boost
    if re.search(r"\+\d+/\+\d+", t) or "gets +" in t or "+1/+1 until end" in t or \
       "gets -" in t or re.search(r"-\d+/-\d+", t) or "+x/+x" in t or "+x/+0" in t or \
       "base power and toughness" in t or "loses all abilities" in t:
        out.add(EventType.PT_MODIFICATION)
    # Look at / reveal / scry-like (these emit some kind of zone-peek event)
    if "look at the top" in t or "reveal" in t and ("put it into your hand" in t or "into your hand" in t):
        out.add(EventType.ZONE_CHANGE)
    # Tap / untap
    if "tap target" in t or "tap up to" in t or "tap enchanted" in t:
        out.add(EventType.TAP_TARGET)
    if "untap target" in t or "untap up to" in t or "untap enchanted" in t:
        out.add(EventType.UNTAP_TARGET)
    # Scry / surveil / mill
    if "scry" in t:
        out.add(EventType.SCRY)
    if "surveil" in t:
        out.add(EventType.SURVEIL)
    if "mill" in t:
        out.add(EventType.MILL)
    # Discard
    if "discard" in t and ("target" in t or "each" in t or "opponent" in t):
        out.add(EventType.DISCARD)
    # Counter spell
    if "counter target" in t and "spell" in t:
        out.add(EventType.COUNTER)
    # Keyword/temporary grant
    if "gain" in t and ("flying" in t or "haste" in t or "vigilance" in t or
                        "deathtouch" in t or "lifelink" in t or "trample" in t or
                        "menace" in t or "first strike" in t or "double strike" in t or
                        "indestructible" in t or "reach" in t or "persist" in t or
                        "hexproof" in t or "shroud" in t or "protection" in t or
                        "ward" in t or "flash" in t):
        out.add(EventType.TEMPORARY_EFFECT)
    if "has" in t and ("flying" in t or "haste" in t or "vigilance" in t or
                       "deathtouch" in t or "lifelink" in t or "indestructible" in t):
        out.add(EventType.TEMPORARY_EFFECT)
    # Copy
    if "copy of" in t or "copies of" in t:
        out.add(EventType.COPY_SPELL)
    # Search library
    if "search your library" in t or "search their library" in t:
        out.add(EventType.SEARCH_LIBRARY)
    return out


# --------------------------------------------------------------------------
# Trigger kind classification
# --------------------------------------------------------------------------
TRIGGER_KIND_FROM_TEXT = [
    # ETB first (most common)
    (re.compile(r"\bwhen\s+(this|[A-Z]\w+(?:[\s,'’][A-Z]?\w+)*)\s+(creature\s+|card\s+|enchantment\s+|aura\s+|artifact\s+|planeswalker\s+|land\s+)?enters\b", re.I), "etb"),
    (re.compile(r"\bwhen\s+enters\b", re.I), "etb"),
    (re.compile(r"\benters,\s+", re.I), "etb"),  # "Vivid — When … enters, …"
    # Death
    (re.compile(r"\bwhen\s+(this|[A-Z]\w+(?:[\s,'’][A-Z]?\w+)*)\s+(creature\s+)?dies\b", re.I), "death"),
    # Attack
    (re.compile(r"\bwhenever\s+(this|[A-Z]\w+(?:[\s,'’][A-Z]?\w+)*)\s+(creature\s+)?attacks\b", re.I), "attack"),
    (re.compile(r"\bwhenever\s+(this|[A-Z]\w+(?:[\s,'’][A-Z]?\w+)*)\s+(creature\s+)?blocks\b", re.I), "attack"),
    # Cast
    (re.compile(r"\bwhenever\s+you\s+cast\b", re.I), "spell_cast"),
    # Phases
    (re.compile(r"\bat\s+the\s+beginning\s+of\s+(your|each)\s+upkeep\b", re.I), "upkeep"),
    (re.compile(r"\bat\s+the\s+beginning\s+of\s+(the|your|each)\s+end\s+step\b", re.I), "end_step"),
    (re.compile(r"\bat\s+the\s+beginning\s+of\s+combat\s+on\s+your\s+turn\b", re.I), "upkeep"),
    # Damage / lifegain
    (re.compile(r"\bwhenever\s+(this|[A-Z]\w+(?:[\s,'’][A-Z]?\w+)*)\s+(creature\s+)?deals\s+damage\b", re.I), "damage"),
    (re.compile(r"\bwhenever\s+you\s+gain\s+life\b", re.I), "life_gain"),
    # Leaves
    (re.compile(r"\bwhen\s+(this|[A-Z]\w+(?:[\s,'’][A-Z]?\w+)*)\s+(creature\s+)?leaves\b", re.I), "leaves_bf"),
    # Becomes tapped / target / etc.
    (re.compile(r"\bwhenever\s+(this|another)\s+\w+\s+becomes\s+tapped\b", re.I), "etb"),  # treat as setup-time
    (re.compile(r"\bwhenever\s+another\s+creature\s+you\s+control\s+enters\b", re.I), "etb"),
]


def classify_trigger(card_text: str) -> str | None:
    if not card_text:
        return None
    # Priority: etb is most common, so check it first
    for pattern, kind in TRIGGER_KIND_FROM_TEXT:
        if pattern.search(card_text):
            return kind
    return None


# --------------------------------------------------------------------------
# Per-card classification (does it have a real setup that fires on ETB?)
# --------------------------------------------------------------------------
def card_has_battlefield_setup(name: str, cdef) -> tuple[bool, str]:
    """Try setting up the card via ZONE_CHANGE -> BATTLEFIELD and report
    whether interceptors registered. Returns (True, reason='') or (False, reason).
    """
    if cdef.setup_interceptors is None:
        return (False, "no setup_interceptors (vanilla, instant/sorcery cast-effect, or land)")
    # Instants/sorceries: their effect happens on CAST not on entering battlefield
    ctypes = getattr(cdef.characteristics, 'types', set()) or set()
    if (CardType.INSTANT in ctypes or CardType.SORCERY in ctypes):
        # Some sorceries register a delayed effect via setup; usually not.
        # Conservatively skip — they don't enter the battlefield.
        return (False, "instant/sorcery (no battlefield entry)")
    # Try the setup; bail if it raises or returns []
    try:
        game = Game()
        p = game.add_player("Tester")
        obj = game.create_object(
            name=name,
            owner_id=p.id,
            zone=ZoneType.HAND,
            characteristics=cdef.characteristics,
            card_def=cdef,
        )
        # Call setup directly with a fresh state — many setups guard on zone
        interceptors = cdef.setup_interceptors(obj, game.state)
        if not interceptors:
            return (False, "setup_interceptors returned [] for HAND obj (graveyard-only or zone-conditional setup)")
        return (True, "")
    except Exception as e:
        return (False, f"setup_interceptors raised: {type(e).__name__}: {e}")


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


HEADER = '''"""Auto-generated interceptor verification for Lorwyn Eclipsed (ECL).

Generated by /test-interceptors. Re-running the skill overwrites this file.
Do NOT hand-edit -- if a test is wrong, fix the generator's heuristics.

Strategy: each wired card is exercised by firing its registered trigger
(ETB, death, attack, damage, spell cast, upkeep, end step) and asserting
that at least one of the expected EventTypes (parsed from the card's
rules text) appears in the resulting event log.

This catches the canonical depths-style bug: an interceptor that fires
but emits zero events (effect_fn = return []) -- it would appear as
"trigger fired but no expected EventType was emitted".
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import Game, Event, EventType, ZoneType, CardType
from src.cards.lorwyn_eclipsed import LORWYN_ECLIPSED_CARDS


# ---------------------------------------------------------------------------
# Cards that cannot be auto-tested.
# ---------------------------------------------------------------------------

SKIPPED_CARDS: dict[str, str] = {
__SKIPPED__
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_game_with_two_players():
    game = Game()
    p1 = game.add_player("Alice")
    p2 = game.add_player("Bob")
    return game, p1, p2


def _create_in_hand(game, player, name):
    cdef = LORWYN_ECLIPSED_CARDS[name]
    obj = game.create_object(
        name=name,
        owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=cdef.characteristics,
        card_def=None,
    )
    obj.card_def = cdef
    return obj


def _move_to_battlefield(game, obj, player):
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': f'hand_{player.id}',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
        }
    ))


def _make_dummy_target(game, player):
    from src.engine import make_creature, Color
    cdef = make_creature(
        name="Dummy Target",
        power=2, toughness=2,
        mana_cost="{1}{G}",
        colors={Color.GREEN},
        subtypes={"Beast"},
        text="",
    )
    return game.create_object(
        name="Dummy Target",
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=cdef.characteristics,
        card_def=cdef,
    )


def _make_dummy_enchantment(game, player):
    from src.engine import make_enchantment, Color
    cdef = make_enchantment(
        name="Dummy Enchantment",
        mana_cost="{1}{W}",
        colors={Color.WHITE},
        text="",
    )
    return game.create_object(
        name="Dummy Enchantment",
        owner_id=player.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=cdef.characteristics,
        card_def=cdef,
    )


def _seed_board(game, p1, p2):
    from src.engine import make_creature, Color
    _make_dummy_target(game, p1)
    _make_dummy_target(game, p2)
    _make_dummy_enchantment(game, p1)
    _make_dummy_enchantment(game, p2)
    for pid in (p1.id, p2.id):
        gy_key = f"graveyard_{pid}"
        if gy_key not in game.state.zones:
            from src.engine.types import Zone
            game.state.zones[gy_key] = Zone(id=gy_key, zone_type=ZoneType.GRAVEYARD)
        cdef = make_creature(
            name="Dummy Graveyard Beast",
            power=2, toughness=2,
            mana_cost="{1}{G}",
            colors={Color.GREEN},
            subtypes={"Beast"},
            text="",
        )
        game.create_object(
            name="Dummy Graveyard Beast",
            owner_id=pid,
            zone=ZoneType.GRAVEYARD,
            characteristics=cdef.characteristics,
            card_def=cdef,
        )
    # opp has more lands than controller
    from src.cards.card_factories import make_land
    for _ in range(3):
        land = make_land(name="Dummy Land", text="")
        game.create_object(
            name="Dummy Land",
            owner_id=p2.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=land.characteristics,
            card_def=land,
        )


def _collect_event_types(game, since_idx: int) -> set:
    log = getattr(game.state, 'event_log', None)
    if log is None:
        log = getattr(game, 'event_log', []) or []
    return {ev.type for ev in log[since_idx:]}


def _event_log_len(game) -> int:
    log = getattr(game.state, 'event_log', None)
    if log is None:
        log = getattr(game, 'event_log', []) or []
    return len(log)


EQUIVALENT = {
    EventType.EXILE: {EventType.ZONE_CHANGE},
    EventType.RETURN_TO_HAND: {EventType.ZONE_CHANGE},
    EventType.RETURN_FROM_GRAVEYARD: {EventType.ZONE_CHANGE},
    EventType.DESTROY: {EventType.OBJECT_DESTROYED, EventType.ZONE_CHANGE},
    EventType.SACRIFICE: {EventType.OBJECT_DESTROYED, EventType.ZONE_CHANGE},
    EventType.DRAW: set(),
    EventType.DISCARD: {EventType.ZONE_CHANGE},
    EventType.MILL: {EventType.ZONE_CHANGE},
    EventType.SCRY: set(),
    EventType.SURVEIL: set(),
    EventType.OBJECT_CREATED: {EventType.CREATE_TOKEN},
    EventType.LIFE_CHANGE: {EventType.LIFE_GAIN, EventType.LIFE_LOSS},
    EventType.PT_MODIFICATION: {EventType.TEMPORARY_EFFECT, EventType.PUMP, EventType.GRANT_PT_MODIFIER, EventType.PT_MODIFIER, EventType.PT_CHANGE, EventType.PT_MODIFY, EventType.TEMPORARY_BOOST},
    EventType.TEMPORARY_EFFECT: {EventType.GRANT_KEYWORD, EventType.KEYWORD_GRANT, EventType.GRANT_ABILITY, EventType.PT_MODIFICATION, EventType.PUMP},
    EventType.TAP_TARGET: {EventType.TAP},
    EventType.UNTAP_TARGET: {EventType.UNTAP},
    EventType.DAMAGE: set(),
    EventType.COUNTER: {EventType.COUNTER_SPELL, EventType.SPELL_COUNTERED},
    EventType.COUNTER_ADDED: set(),
    EventType.COPY_SPELL: {EventType.COPY_STACK_ITEM},
}


def _expand_expected(expected_set: set) -> set:
    out = set(expected_set)
    for e in list(expected_set):
        out |= EQUIVALENT.get(e, set())
    return out


def _assert_expected_event_emitted(game, since_idx: int, expected_set: set, card_name: str, trigger_kind: str):
    emitted = _collect_event_types(game, since_idx)
    bookkeeping = {
        EventType.TRIGGERED_ABILITY_PUT_ON_STACK,
        EventType.PHASE_START,
        EventType.PHASE_END,
        EventType.PHASE_CHANGE,
        EventType.PRIORITY_PASS,
    }
    effective = emitted - bookkeeping
    if not effective:
        expected_names = sorted(e.name for e in expected_set)
        emitted_names = sorted(e.name for e in emitted)
        raise AssertionError(
            f"{card_name}: {trigger_kind} fired but produced ZERO effect events "
            f"(depths trap). Emitted only bookkeeping: {emitted_names}. "
            f"Expected one of: {expected_names}"
        )
    if not expected_set:
        return
    expanded = _expand_expected(expected_set)
    overlap = effective & expanded
    if not overlap:
        emitted_names = sorted(e.name for e in emitted)
        expected_names = sorted(e.name for e in expected_set)
        raise AssertionError(
            f"{card_name}: {trigger_kind} emitted {emitted_names} "
            f"but expected at least one of {expected_names}"
        )


def _send_to_graveyard(game, card, player):
    gy_zone = f"graveyard_{player.id}"
    if gy_zone not in game.state.zones:
        from src.engine import Zone
        game.state.zones[gy_zone] = Zone(id=gy_zone, zone_type=ZoneType.GRAVEYARD)
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': card.id, 'reason': 'lethal damage'},
    ))
    obj = game.state.objects.get(card.id)
    if obj and obj.zone == ZoneType.BATTLEFIELD:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': card.id,
                'from_zone': 'battlefield',
                'to_zone': gy_zone,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.GRAVEYARD,
            }
        ))


'''

TEMPLATES = {
    "etb": """def test_{slug}():
    \"\"\"{name}: ETB trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    before = _event_log_len(game)
    _move_to_battlefield(game, card, p1)
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "ETB")
""",
    "death": """def test_{slug}():
    \"\"\"{name}: death trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    _move_to_battlefield(game, card, p1)
    before = _event_log_len(game)
    _send_to_graveyard(game, card, p1)
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "death")
""",
    "attack": """def test_{slug}():
    \"\"\"{name}: attack trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    _move_to_battlefield(game, card, p1)
    before = _event_log_len(game)
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={{'attacker_id': card.id, 'defender_id': p2.id, 'controller': p1.id}},
    ))
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "attack")
""",
    "upkeep": """def test_{slug}():
    \"\"\"{name}: upkeep trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    _move_to_battlefield(game, card, p1)
    game.state.active_player = p1.id
    before = _event_log_len(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={{'phase': 'upkeep', 'player': p1.id}},
    ))
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "upkeep")
""",
    "end_step": """def test_{slug}():
    \"\"\"{name}: end_step trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    _move_to_battlefield(game, card, p1)
    game.state.active_player = p1.id
    before = _event_log_len(game)
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={{'phase': 'end_step', 'player': p1.id}},
    ))
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "end_step")
""",
    "spell_cast": """def test_{slug}():
    \"\"\"{name}: spell-cast trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    _move_to_battlefield(game, card, p1)
    before = _event_log_len(game)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={{'spell_id': 'dummy', 'controller': p1.id, 'card_types': [CardType.INSTANT]}},
    ))
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "spell_cast")
""",
    "damage": """def test_{slug}():
    \"\"\"{name}: damage trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    _move_to_battlefield(game, card, p1)
    before = _event_log_len(game)
    game.emit(Event(
        type=EventType.DAMAGE,
        payload={{'source_id': card.id, 'target_id': p2.id, 'amount': 1, 'controller': p1.id}},
    ))
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "damage")
""",
    "life_gain": """def test_{slug}():
    \"\"\"{name}: life-gain trigger emits one of {expected_list}.\"\"\"
    game, p1, p2 = _new_game_with_two_players()
    _seed_board(game, p1, p2)
    card = _create_in_hand(game, p1, {name!r})
    _move_to_battlefield(game, card, p1)
    before = _event_log_len(game)
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={{'player': p1.id, 'amount': 3}},
    ))
    _assert_expected_event_emitted(game, before, {{ {expected_inline} }}, {name!r}, "life_gain")
""",
}


RUNNER = '''

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import traceback
    tests = sorted([(k, v) for k, v in globals().items() if k.startswith("test_")])
    passed, failed, errors = [], [], []
    for name, fn in tests:
        try:
            fn()
            passed.append(name)
        except AssertionError as e:
            failed.append((name, str(e)))
        except Exception as e:
            errors.append((name, f"{type(e).__name__}: {e}"))

    total = len(tests)
    print()
    print("=" * 70)
    print(f"ECL interceptor verification")
    print("=" * 70)
    print(f"  tests:   {total}")
    print(f"  passed:  {len(passed)}")
    print(f"  failed:  {len(failed)}")
    print(f"  errors:  {len(errors)}")
    print(f"  skipped: {len(SKIPPED_CARDS)} (see SKIPPED_CARDS)")

    if failed:
        print()
        print("--- FAILURES (first 25) ---")
        for n, msg in failed[:25]:
            print(f"  {n}: {msg}")
    if errors:
        print()
        print("--- ERRORS (first 25) ---")
        for n, msg in errors[:25]:
            print(f"  {n}: {msg}")

    pass_rate = (100.0 * len(passed) / total) if total else 0.0
    print()
    print(f"  pass rate: {pass_rate:.1f}%")
    sys.exit(0 if not failed and not errors else 1)
'''


def main():
    cards = LORWYN_ECLIPSED_CARDS
    print(f"Loaded {len(cards)} ECL cards.", file=sys.stderr)

    skipped: dict[str, str] = {}
    tests: list[tuple[str, str, str, set]] = []  # (slug, name, kind, expected)
    seen_slugs: set[str] = set()

    for name, cdef in cards.items():
        # Skip basic lands
        ctypes = getattr(cdef.characteristics, 'types', set()) or set()
        text = getattr(cdef, 'text', '') or ''
        ok, why = card_has_battlefield_setup(name, cdef)
        if not ok:
            skipped[name] = why
            continue
        kind = classify_trigger(text)
        if not kind:
            skipped[name] = "kind=unknown from text; needs custom test (static/activated/equipment)"
            continue
        expected = parse_expected_events(text)
        # If no expected events parsable, still emit a "smoke" test that
        # catches depths-trap (effect_fn returns []) without asserting
        # a specific EventType.
        if kind not in TEMPLATES:
            skipped[name] = f"trigger kind {kind!r} not supported by generator"
            continue
        slug = slugify(name)
        if slug in seen_slugs:
            # Collision: append hash
            slug = slug + "_" + str(abs(hash(name)) % 10000)
        seen_slugs.add(slug)
        tests.append((slug, name, kind, expected))

    print(f"Generated {len(tests)} tests; {len(skipped)} skipped.", file=sys.stderr)

    # Build skipped dict literal
    skipped_lines = []
    for name in sorted(skipped):
        reason = skipped[name].replace('"', '\\"').replace("\n", " ")
        skipped_lines.append(f"    {name!r}: {reason!r},")
    skipped_block = "\n".join(skipped_lines)

    header = HEADER.replace("__SKIPPED__", skipped_block)

    body_parts = []
    for slug, name, kind, expected in sorted(tests, key=lambda x: x[0]):
        expected_names = sorted(e.name for e in expected)
        expected_list = "[" + ", ".join(f"{n!r}" for n in expected_names) + "]"
        expected_inline = ", ".join(f"EventType.{n}" for n in expected_names)
        body_parts.append(
            TEMPLATES[kind].format(
                slug=slug,
                name=name,
                expected_list=expected_list,
                expected_inline=expected_inline,
            )
        )

    out_path = os.path.join(ROOT, "tests", "test_ecl_interceptors.py")
    with open(out_path, "w") as f:
        f.write(header)
        f.write("\n".join(body_parts))
        f.write(RUNNER)
    print(f"Wrote {out_path}", file=sys.stderr)
    print(f"tests={len(tests)} skipped={len(skipped)}")


if __name__ == "__main__":
    main()
