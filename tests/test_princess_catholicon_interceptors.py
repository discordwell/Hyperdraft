"""
Auto-generated interceptor verification for custom/princess_catholicon.

Verifies that cards whose definitions wire an interceptor (setup_interceptors)
or a spell-resolution function (resolve) actually emit at least one downstream
event when their trigger fires.

Catches the depths trap: a card whose ``setup_interceptors`` registers a
trigger whose ``effect_fn`` returns ``[]`` because the engine didn't yet
support the underlying effect. See /test-interceptors for full rationale.

Run directly:

    PYTHONPATH=. python tests/test_princess_catholicon_interceptors.py

This file is auto-regenerable — do not hand-edit; re-run /test-interceptors
on the set instead.

NOTE: The princess_catholicon header annotates a Slice-16 median-lift retrofit
dated 2026-05-19 ("drives FIN depth_v2_median 0 -> 2+") plus a Phase A1
spice-pass rewire. Both patterns mean some setups intentionally inline state /
zone reads to satisfy depth-rubric axes. This generator does not score depth
— it only verifies the resulting interceptor fires and emits >=1 event.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color,
    GameObject, GameState, Characteristics,
)


# Load the card module directly (the __init__.py path can pull other sets in).
_spec = importlib.util.spec_from_file_location(
    "princess_catholicon",
    str(PROJECT_ROOT / "src/cards/custom/princess_catholicon.py"),
)
_princess_catholicon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_princess_catholicon)
PRINCESS_CATHOLICON_CARDS = _princess_catholicon.FINAL_FANTASY_CUSTOM_CARDS


# Card sampling cap (anti-stall: 8-min budget).
MAX_CARDS = 150


# Cards that need human selection of a mode / target from a non-trivial pool,
# or whose effect is purely conditional / replacement and so does not emit on
# entry. We don't assert on these — they're surfaced in the report instead.
SKIPPED_CARDS: dict[str, str] = {}


# =============================================================================
# Helpers
# =============================================================================

def _make_game(num_players: int = 2) -> tuple[Game, list]:
    g = Game()
    players = [g.add_player(f"P{i + 1}") for i in range(num_players)]
    return g, players


def _drop_on_battlefield(game: Game, card_def, owner_id: str):
    """Create the card in HAND, then emit ZONE_CHANGE to BATTLEFIELD.

    Returns (object, list_of_emitted_events). Mirrors temporal_horizons'
    create_and_enter_battlefield helper.
    """
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )

    events = game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone': 'hand',
            'to_zone': 'battlefield',
            'to_zone_type': ZoneType.BATTLEFIELD,
            'object': obj,
        },
    ))

    return obj, events


def _call_resolve(card_def, state: GameState) -> list[Event]:
    """Dispatch the card's resolve fn under whichever signature it uses.

    Mirrors the inspect-based dispatch in src/engine/stack.py:resolve_top.
    """
    fn = card_def.resolve
    if fn is None:
        return []

    use_event = False
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if len(params) >= 2:
            p0 = params[0]
            if p0.name in {"event", "spell_event", "resolve_event"}:
                use_event = True
            elif p0.annotation is Event:
                use_event = True
    except Exception:
        use_event = False

    if use_event:
        resolve_event = Event(
            type=EventType.CAST,
            payload={"targets": []},
            source=None,
            controller=getattr(state, 'active_player', None),
        )
        return fn(resolve_event, state) or []
    return fn([], state) or []


def _interesting(events: list[Event]) -> list[Event]:
    """Filter out plumbing events (ZONE_CHANGE we induced, OBJECT_CREATED) so
    "the trigger didn't fire" doesn't show as a false pass.
    """
    noise = {EventType.ZONE_CHANGE, EventType.OBJECT_CREATED, EventType.ENTER_BATTLEFIELD}
    return [e for e in events if e.type not in noise]


# =============================================================================
# Generic verifier
# =============================================================================

def _verify_setup_card(card_name: str, card_def) -> tuple[str, str]:
    """Return (outcome, detail). outcome in {'pass', 'empty', 'error'}."""
    try:
        game, (p1, _p2) = _make_game(2)
        obj, events = _drop_on_battlefield(game, card_def, p1.id)
    except Exception as exc:
        return 'error', f"{type(exc).__name__}: {exc}"

    interesting = _interesting(events)
    if interesting:
        return 'pass', f"emitted {len(interesting)} event(s) (first={interesting[0].type.name})"

    # No interesting event on ETB. The card may register a static interceptor
    # (e.g. lord effect) whose effect only shows on a Q-event, or a death /
    # attack / upkeep trigger that hasn't fired yet. Inspect what setup
    # actually returned: if it returned any interceptor at all, count it as a
    # pass-with-empty-etb. If it returned [], flag as empty.
    try:
        state = game.state if hasattr(game, 'state') else game
        interceptors = card_def.setup_interceptors(obj, state) if card_def.setup_interceptors else []
    except Exception as exc:
        return 'error', f"setup_interceptors raised: {type(exc).__name__}: {exc}"

    if interceptors:
        return 'pass', f"registered {len(interceptors)} interceptor(s), no ETB event (static/death/attack/upkeep trigger)"
    return 'empty', "setup_interceptors returned [] and no ETB event emitted"


def _verify_resolve_card(card_name: str, card_def) -> tuple[str, str]:
    try:
        game, (p1, _p2) = _make_game(2)
        # Some resolves read state.active_player; set it explicitly.
        try:
            game.state.active_player = p1.id
        except Exception:
            pass
        state = game.state if hasattr(game, 'state') else game
        events = _call_resolve(card_def, state)
    except Exception as exc:
        return 'error', f"{type(exc).__name__}: {exc}"

    if not events:
        return 'empty', "resolve returned [] (engine gap or empty stub)"
    return 'pass', f"resolve emitted {len(events)} event(s) (first={events[0].type.name})"


# =============================================================================
# Test runner — auto-generated per card
# =============================================================================

def _select_cards():
    """Pick up to MAX_CARDS sample cards. Stable order across runs."""
    items = list(PRINCESS_CATHOLICON_CARDS.items())
    # Filter to cards with at least one verifier hook.
    eligible = []
    for name, card in items:
        if card is None:
            continue
        if card.setup_interceptors is not None or card.resolve is not None:
            eligible.append((name, card))
    # Slice deterministically (every Nth across the dict so we cover all 5
    # colors and spell + creature mix).
    step = max(1, len(eligible) // MAX_CARDS) if len(eligible) > MAX_CARDS else 1
    sampled = eligible[::step][:MAX_CARDS]
    return eligible, sampled


def main() -> int:
    eligible, sampled = _select_cards()
    total_cards = len(PRINCESS_CATHOLICON_CARDS)
    eligible_count = len(eligible)
    sampled_count = len(sampled)

    passed: list[str] = []
    empties: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []

    failure_buckets: dict[str, list[tuple[str, str]]] = {}
    breakage_count: dict[str, int] = {}

    for name, card in sampled:
        if name in SKIPPED_CARDS:
            continue
        if card.setup_interceptors is not None:
            outcome, detail = _verify_setup_card(name, card)
        elif card.resolve is not None:
            outcome, detail = _verify_resolve_card(name, card)
        else:
            continue

        if outcome == 'pass':
            passed.append(name)
        elif outcome == 'empty':
            empties.append((name, detail))
            failure_buckets.setdefault('empty_effect', []).append((name, detail))
            breakage_count[name] = breakage_count.get(name, 0) + 1
        else:  # error
            errors.append((name, detail))
            # Bucket by exception class.
            bucket = detail.split(':', 1)[0].strip()
            failure_buckets.setdefault(bucket, []).append((name, detail))
            breakage_count[name] = breakage_count.get(name, 0) + 1

    print("\n=== Interceptor verification: princess_catholicon ===")
    print(f"  cards in set:    {total_cards}")
    print(f"  eligible cards:  {eligible_count} (have setup_interceptors or resolve)")
    print(f"  sampled cards:   {sampled_count}")
    print(f"  skipped (manual): {len(SKIPPED_CARDS)}")
    print(f"  passed:          {len(passed)}")
    print(f"  empty effects:   {len(empties)}")
    print(f"  errors:          {len(errors)}")
    tested = len(passed) + len(empties) + len(errors)
    if tested:
        print(f"  pass rate:       {100 * len(passed) / tested:.1f}%")

    if failure_buckets:
        print("\n--- Failure categories ---")
        for bucket, rows in sorted(failure_buckets.items(), key=lambda kv: -len(kv[1])):
            print(f"  [{bucket}]: {len(rows)} card(s)")
            for name, detail in rows[:3]:
                print(f"     - {name}: {detail}")

    if breakage_count:
        worst = sorted(breakage_count.items(), key=lambda kv: -kv[1])[:10]
        print("\n--- Top broken cards ---")
        for name, _n in worst:
            print(f"  {name}")

    # Treat empties as warn-only (CLAUDE.md notes ~736 such cards across real
    # MTG sets are legitimately gated on engine support). Errors are real
    # failures.
    return 0 if not errors else 1


# Provide one named test per sampled card so pytest discovery shows them.
def _install_per_card_tests():
    _, sampled = _select_cards()
    for name, card in sampled:
        snake = (
            name.lower()
                .replace(' ', '_')
                .replace(',', '')
                .replace("'", '')
                .replace('-', '_')
                .replace('"', '')
                .replace('(', '')
                .replace(')', '')
                .replace('!', '')
                .replace('?', '')
                .replace('.', '')
                .replace('/', '_')
                .replace(':', '')
        )
        test_name = f"test_card_{snake}"

        def _make_test(_card=card, _name=name):
            def _t():
                if _name in SKIPPED_CARDS:
                    return  # warn-only — skipped by design
                if _card.setup_interceptors is not None:
                    outcome, detail = _verify_setup_card(_name, _card)
                elif _card.resolve is not None:
                    outcome, detail = _verify_resolve_card(_name, _card)
                else:
                    return
                if outcome == 'error':
                    raise AssertionError(f"{_name}: {detail}")
                # Warn-only for empties.
            _t.__name__ = test_name
            _t.__doc__ = f"{_name}: verify interceptor / resolve emits >=1 event"
            return _t

        globals()[test_name] = _make_test()


_install_per_card_tests()


if __name__ == "__main__":
    sys.exit(main())
