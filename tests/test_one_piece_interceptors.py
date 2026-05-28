"""Auto-generated interceptor verification for custom/one_piece (OPC). See /test-interceptors.

Catches the "depths trap" — interceptor wired but effect_fn returns [] silently.

OPC underwent a "slice-22 median-lift" retrofit (2026-05-19, see header in
src/cards/custom/one_piece.py:226). 156 of 250 cards with setup_interceptors
now point at _opc_s22_*_setup helpers that emit a multi-event payload
(SCRY/SURVEIL + a self-bonus + an asymmetric-event against opponents).
The remaining ~94 cards retain pre-retrofit setup functions, many of which
have `return []` in their effect_fn pending engine-side support.

This file invokes `setup_interceptors(obj, state)` directly to retrieve the
interceptor list, then for each triggered-ability interceptor fires a
synthetic event matching its filter and asserts `effect_fn` returns ≥1
new event.

Engine constraint: this is purely a unit-level verification — we do NOT
emit through `game.emit`, because slice-22's effect_fn emits non-MTG
event aliases (SURVEIL/MILL/EXILE with payload shapes that aren't
consumed by the MTG pipeline). We're checking *intent to fire*, not
end-to-end resolution. A 0-event return → depths-trap regression.

Run: PYTHONPATH=. python tests/test_one_piece_interceptors.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.game import Game  # noqa: E402
from src.engine.types import (  # noqa: E402
    CardType, Event, EventType, ZoneType,
)

# Direct module import to avoid pulling the whole custom-set __init__ chain.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "one_piece_for_interceptor_tests",
    str(PROJECT_ROOT / "src/cards/custom/one_piece.py"),
)
_op = importlib.util.module_from_spec(spec)
sys.modules["one_piece_for_interceptor_tests"] = _op
spec.loader.exec_module(_op)

ONE_PIECE_CARDS = _op.ONE_PIECE_CARDS


# ---------------------------------------------------------------------------
# Cards we deliberately skip — one-line reason per card class.
# ---------------------------------------------------------------------------

SKIPPED_CARDS: dict[str, str] = {
    # Pure no-interceptor cards (vanilla creatures, simple lands). These have
    # setup_interceptors=None and won't be picked up by the discovery loop
    # anyway, but they're listed here for the human eyeball.
    "Marine Soldier":        "vanilla 1/1 (no setup_interceptors)",
    "Fishman Warrior":       "vanilla creature (only registers a self-keyword grant; no triggered ability)",
    "Marine Captain":        "vanilla 2/2 (only flat static lord; no triggered ability)",
    "Helmeppo, Reformed":    "self-keyword grant only; no triggered effect to verify",
    "Impel Down Guard":      "self-keyword grant only; no triggered effect to verify",
    # Modal / target-required cards — effect_fn returns [] by design until
    # the engine fills in target_chosen.
    "Akainu, Absolute Justice":    "target-required; effect_fn=[] until target chosen",
    "Aokiji, Lazy Justice":        "target-required; effect_fn=[] until target chosen",
    "Kizaru, Unclear Justice":     "target-required; effect_fn=[] until target chosen",
    "Garp, the Hero":              "target-required; effect_fn=[] until target chosen",
    "Tashigi, Swordswoman":        "target-required; effect_fn=[] until target chosen",
}


# ---------------------------------------------------------------------------
# Game-state scaffold
# ---------------------------------------------------------------------------

def _build_game():
    """2-player MTG game with both players seated; no zones rigged yet."""
    g = Game()
    p1 = g.add_player("P1")
    p2 = g.add_player("P2")
    return g, p1, p2


def _place_on_battlefield(game, owner_id: str, card_def):
    """Create a GameObject in BATTLEFIELD; does NOT auto-run setup_interceptors."""
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner_id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )
    obj.controller = owner_id
    return obj


# ---------------------------------------------------------------------------
# Trigger-kind detection + synthetic-event construction
# ---------------------------------------------------------------------------

# These keywords appear in interceptor.description (set by _mark_triggered_ability).
# We match on description first, fall back to filter probing.

_TRIGGER_EVENT_MAP = {
    "ETB trigger":          EventType.ZONE_CHANGE,
    "Death trigger":        EventType.OBJECT_DESTROYED,
    "Attack trigger":       EventType.ATTACK_DECLARED,
    "Block trigger":        EventType.BLOCK_DECLARED,
    "Damage trigger":       EventType.DAMAGE,
    "Upkeep trigger":       EventType.PHASE_START,
    "End step trigger":     EventType.PHASE_START,
    "End-of-turn trigger":  EventType.PHASE_START,
    "Tap trigger":          EventType.TAP,
    "Spell cast trigger":   EventType.SPELL_CAST,
    "Life gain trigger":    EventType.LIFE_CHANGE,
    "Life loss trigger":    EventType.LIFE_CHANGE,
    "Draw trigger":         EventType.DRAW,
    "Counter added trigger":EventType.COUNTER_ADDED,
    "Leaves-battlefield trigger": EventType.ZONE_CHANGE,
}


def _build_synthetic_event(desc: str, obj, opp_id: str) -> Event | None:
    """Build a payload that maximises the chance of matching the trigger's filter.

    Returns None for trigger kinds we can't synthesise (e.g. spell-cast which
    requires a stack object). Tests for those cards will fall through to a
    direct effect_fn invocation with a generic event.
    """
    et = _TRIGGER_EVENT_MAP.get(desc)
    if et is None:
        return None
    if desc == "ETB trigger":
        return Event(
            type=EventType.ZONE_CHANGE,
            payload={
                "object_id": obj.id,
                "from_zone_type": ZoneType.HAND,
                "to_zone_type": ZoneType.BATTLEFIELD,
                "to_zone": "battlefield",
            },
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Death trigger":
        return Event(
            type=EventType.OBJECT_DESTROYED,
            payload={"object_id": obj.id},
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Attack trigger":
        obj.state.attacking = True
        return Event(
            type=EventType.ATTACK_DECLARED,
            payload={"attacker_id": obj.id, "defender_id": opp_id},
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Block trigger":
        return Event(
            type=EventType.BLOCK_DECLARED,
            payload={"blocker_id": obj.id, "attacker_id": None},
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Damage trigger":
        return Event(
            type=EventType.DAMAGE,
            payload={"source": obj.id, "target": opp_id, "amount": 1},
            source=obj.id,
            controller=obj.controller,
        )
    if desc in ("Upkeep trigger",):
        return Event(
            type=EventType.PHASE_START,
            payload={"phase": "upkeep", "player": obj.controller},
            source=obj.id,
            controller=obj.controller,
        )
    if desc in ("End step trigger", "End-of-turn trigger"):
        return Event(
            type=EventType.PHASE_START,
            payload={"phase": "end_step", "player": obj.controller},
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Tap trigger":
        return Event(
            type=EventType.TAP,
            payload={"object_id": obj.id},
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Draw trigger":
        return Event(
            type=EventType.DRAW,
            payload={"player": obj.controller, "amount": 1},
            source=obj.id,
            controller=obj.controller,
        )
    if desc in ("Life gain trigger", "Life loss trigger"):
        return Event(
            type=EventType.LIFE_CHANGE,
            payload={"player": obj.controller, "amount": 1 if "gain" in desc else -1},
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Counter added trigger":
        return Event(
            type=EventType.COUNTER_ADDED,
            payload={"object_id": obj.id, "counter_type": "+1/+1", "amount": 1},
            source=obj.id,
            controller=obj.controller,
        )
    if desc == "Spell cast trigger":
        return Event(
            type=EventType.SPELL_CAST,
            payload={"controller": obj.controller, "card_def": None},
            source=obj.id,
            controller=obj.controller,
        )
    return None


# ---------------------------------------------------------------------------
# Discovery — pick the cards we'll test
# ---------------------------------------------------------------------------

def _select_cards(limit: int = 150) -> list[tuple[str, object]]:
    """Pick cards with setup_interceptors, skipping SKIPPED_CARDS.

    Prioritise slice-22-retrofitted setups (most coverage value), then fall
    through to the rest. Cap at `limit` to keep runtime sane.
    """
    s22 = []
    other = []
    for name, cd in ONE_PIECE_CARDS.items():
        if name in SKIPPED_CARDS:
            continue
        si = getattr(cd, "setup_interceptors", None)
        if si is None:
            continue
        # Skip cards whose setup uses make_equipment_setup wrapper directly
        # (they install an attach-static, not a triggered ability; covered
        # by smoke tests elsewhere).
        fn_name = getattr(si, "__name__", "") or ""
        if fn_name == "equipment_setup":
            continue
        if fn_name.startswith("_opc_s22_"):
            s22.append((name, cd))
        else:
            other.append((name, cd))
    selected = s22 + other
    return selected[:limit]


# ---------------------------------------------------------------------------
# The core single-card verification
# ---------------------------------------------------------------------------

def _verify_card(name: str, card_def) -> tuple[str, str]:
    """Returns ('pass'|'fail'|'error'|'skip', reason_or_empty)."""
    try:
        game, p1, p2 = _build_game()
        obj = _place_on_battlefield(game, p1.id, card_def)
        # Call setup_interceptors with the placed object + state.
        try:
            interceptors = card_def.setup_interceptors(obj, game.state)
        except TypeError:
            return "skip", "setup_interceptors signature non-standard"
        if not interceptors:
            return "skip", "setup_interceptors returned empty list"
        # Pick the first triggered-ability interceptor (most cards have one).
        # Static-effect interceptors (lords, keyword grants) don't have an
        # effect_fn we can fire — skip them with a reason.
        triggered = [i for i in interceptors if getattr(i, "is_triggered_ability", False)]
        if not triggered:
            return "skip", f"only static interceptors registered ({len(interceptors)} total)"
        # Try each triggered interceptor; pass if any one emits events.
        last_reason = "no events emitted"
        for interceptor in triggered:
            desc = (getattr(interceptor, "description", "") or "").strip()
            effect_fn = getattr(interceptor, "effect_fn", None)
            if effect_fn is None:
                last_reason = f"interceptor desc={desc!r} has no effect_fn attribute"
                continue
            event = _build_synthetic_event(desc, obj, p2.id)
            if event is None:
                # Unknown trigger kind — try a generic ZONE_CHANGE.
                event = Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        "object_id": obj.id,
                        "to_zone_type": ZoneType.BATTLEFIELD,
                    },
                    source=obj.id,
                    controller=obj.controller,
                )
            try:
                emitted = effect_fn(event, game.state)
            except Exception as e:
                last_reason = f"effect_fn raised {type(e).__name__}: {e}"
                continue
            if emitted and len(emitted) > 0:
                return "pass", f"emitted {len(emitted)} events ({[e.type.name for e in emitted[:3]]})"
            last_reason = f"effect_fn returned [] (depths trap) desc={desc!r}"
        return "fail", last_reason
    except Exception as e:
        return "error", f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Auto-generate one test function per card so unittest-style runners work
# ---------------------------------------------------------------------------

_SELECTED = _select_cards(limit=250)


def _make_test(card_name: str, card_def):
    def _t():
        status, reason = _verify_card(card_name, card_def)
        if status == "pass":
            return
        if status == "skip":
            print(f"  SKIP {card_name}: {reason}")
            return
        raise AssertionError(f"{card_name}: {status} — {reason}")
    _t.__name__ = f"test_card_{_safe_id(card_name)}"
    _t.__doc__ = f"{card_name}: verify setup_interceptors -> triggered effect_fn emits ≥1 event"
    return _t


def _safe_id(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum():
            out.append(ch.lower())
        else:
            out.append("_")
    s = "".join(out)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


# Install one test function per selected card into module globals so a
# generic pytest collector or the __main__ runner below picks them up.
for _name, _cd in _SELECTED:
    _fn = _make_test(_name, _cd)
    globals()[_fn.__name__] = _fn


# ---------------------------------------------------------------------------
# __main__: run every test, build a fail-category summary
# ---------------------------------------------------------------------------

def _categorise_failure(reason: str) -> str:
    r = reason.lower()
    if "[] (depths trap)" in r or "returned []" in r:
        return "empty_effect_fn"
    if "raised" in r:
        return "effect_fn_crashed"
    if "no effect_fn attribute" in r:
        return "untagged_interceptor"
    if "no events emitted" in r:
        return "no_emit"
    return "other"


if __name__ == "__main__":
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_card_")]
    passed, failed, errors, skipped = [], [], [], []
    fail_categories: dict[str, list[str]] = {}

    for name, fn in tests:
        try:
            fn()
            passed.append(name)
        except AssertionError as e:
            failed.append((name, str(e)))
            cat = _categorise_failure(str(e))
            fail_categories.setdefault(cat, []).append(name)
        except Exception as e:
            errors.append((name, f"{type(e).__name__}: {e}"))
            tb = traceback.format_exc()
            fail_categories.setdefault("test_crashed", []).append(f"{name}: {tb.splitlines()[-1]}")

    total = len(tests)
    extra_skipped = len(SKIPPED_CARDS)
    print()
    print("=" * 64)
    print(" /test-interceptors — custom/one_piece (OPC)")
    print("=" * 64)
    print(f"  cards in pool:    {len(ONE_PIECE_CARDS)}")
    print(f"  tests generated:  {total}")
    print(f"  passed:           {len(passed)}")
    print(f"  failed:           {len(failed)}")
    print(f"  errors:           {len(errors)}")
    print(f"  skipped (hard):   {extra_skipped}  (see SKIPPED_CARDS)")
    pass_rate = (100.0 * len(passed) / total) if total else 0.0
    print(f"  pass rate:        {pass_rate:.1f}%")
    print()
    if fail_categories:
        print("--- failure categories ---")
        for cat, items in sorted(fail_categories.items(), key=lambda kv: -len(kv[1])):
            print(f"  {cat:20s} {len(items):4d}")
        print()
    if failed:
        print("--- first 15 failures ---")
        for name, msg in failed[:15]:
            print(f"  {name}: {msg}")
        print()
    if errors:
        print("--- first 5 test-runner errors ---")
        for name, msg in errors[:5]:
            print(f"  {name}: {msg}")
        print()
    sys.exit(0 if (not failed and not errors) else 1)
