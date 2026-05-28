"""
Auto-generated interceptor verification for custom/my_hero_academia.

See `.claude/commands/test-interceptors.md`. This file dynamically iterates
every card in MY_HERO_ACADEMIA_CARDS that wires `setup_interceptors`, drops
it on the battlefield (firing the appropriate canonical trigger event for
its detected pattern), and asserts at least one non-empty event is emitted.

Retrofit pattern detected: "Slice-21 median-lift setups (2026-05-19)"
"drives MHA depth_v2_median 0 -> 2+" — most ETB triggers emit SCRY +
LIFE_CHANGE, attack triggers emit SCRY + LIFE_CHANGE drain.

Categorizes failures into:
  - empty_effect: trigger fires, 0 downstream events
  - no_trigger: emitted canonical event but interceptor never reacted
  - error: exception raised during setup or trigger
  - skipped: modal / target-choice / saga / replacement / aura-static
"""

import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.types import (
    Event, EventType, ZoneType, CardType, Color,
    Characteristics, GameObject, ObjectState,
    InterceptorPriority
)
from src.engine.game import Game

# Import my_hero_academia directly without going through custom __init__
import importlib.util
spec = importlib.util.spec_from_file_location(
    "my_hero_academia",
    str(PROJECT_ROOT / "src/cards/custom/my_hero_academia.py")
)
mha_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mha_module)
MHA_CARDS = mha_module.MY_HERO_ACADEMIA_CARDS


# Cards we cannot meaningfully auto-test — modal, target-choice, saga,
# replacement effects, equipment / aura statics that need an attached
# creature, or activated abilities that need a cost payment.
SKIPPED_CARDS = {
    "Hero License": "aura static — needs attached creature",
    "Provisional License": "aura static — needs attached creature",
    "League Hideout": "land-style static, no battlefield trigger to fire",
    "Quirk Singularity": "static enchantment — no per-trigger emission",
    "Symbol of Hope": "static enchantment with conditional trigger",
}


# =============================================================================
# Helpers
# =============================================================================

def make_game(num_players: int = 2):
    g = Game()
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob") if num_players >= 2 else None
    return g, p1, p2


def install_event_tracker(game):
    """Wrap game.emit so we can inspect every event emitted after install."""
    log = []
    original_emit = game.emit

    def tracker(event):
        result = original_emit(event)
        # Track the event itself plus anything emitted from interceptors.
        log.append(event)
        if isinstance(result, list):
            for e in result:
                if isinstance(e, Event):
                    log.append(e)
        return result

    game.emit = tracker
    return log


def create_card_on_battlefield(game, player_id, card_name, fire_etb=True):
    """Create the card in HAND then move to BATTLEFIELD via ZONE_CHANGE.

    Mirrors the harry_potter / spider_man scaffold: avoids early setup by
    not passing card_def into create_object, then sets card_def on the
    object so `_handle_zone_change` runs the setup the canonical way.
    """
    card_def = MHA_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None
    )
    obj.card_def = card_def

    if fire_etb:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': ZoneType.HAND,
                'to_zone_type': ZoneType.BATTLEFIELD
            },
            source=obj.id,
            controller=obj.controller
        ))
    return obj


def fire_attack(game, attacker):
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'defending_player': 'opponent'},
        source=attacker.id,
        controller=attacker.controller
    ))


def fire_death(game, obj):
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD
        },
        source=obj.id,
        controller=obj.controller
    ))


# Event types we count as "real effects emitted by the card".
# (We exclude infrastructure events that are not effect output.)
def _build_effectful_set():
    names = [
        'LIFE_CHANGE', 'DRAW', 'SCRY', 'DAMAGE', 'DISCARD',
        'SACRIFICE', 'OBJECT_DESTROYED', 'COUNTER_ADDED',
        'PT_MODIFICATION', 'CREATE_TOKEN', 'OBJECT_CREATED',
        'ACTIVATE', 'MILL', 'SURVEIL',
        'TAP', 'TAP_TARGET', 'UNTAP', 'UNTAP_TARGET',
        'REMOVE_ABILITIES', 'TEMPORARY_BOOST', 'TEMPORARY_PT_CHANGE',
        'EXILE', 'CONDITIONAL_COUNTERS',
    ]
    return {getattr(EventType, n) for n in names if hasattr(EventType, n)}


EFFECTFUL_EVENT_TYPES = _build_effectful_set()


# Keywords whose presence-only text marks a card as a self-keyword grant
# (no effectful event will fire on ETB).
KEYWORD_ONLY_TEXTS = {
    'flying', 'trample', 'haste', 'lifelink', 'vigilance', 'menace',
    'first strike', 'double strike', 'deathtouch', 'hexproof', 'reach',
    'defender', 'flash', 'indestructible', 'ward', 'protection',
}


def card_wires_setup(card_def) -> bool:
    return bool(getattr(card_def, 'setup_interceptors', None))


def card_is_static_only(card_def) -> bool:
    """Static-only cards (lord effects, keyword grants, aura statics)
    register interceptors but emit no events on ETB. We treat them as
    skipped to avoid false-positive failures."""
    text = (getattr(card_def, 'text', '') or '').strip().lower()

    # Bare keyword-only text — e.g. "Lifelink" or "Flying, vigilance".
    if text:
        tokens = {t.strip(' .') for t in text.replace(',', ' ').split()}
        # Filter out tiny connector words
        meaningful = {t for t in tokens if len(t) > 2}
        if meaningful and meaningful.issubset(KEYWORD_ONLY_TEXTS | {'and'}):
            return True
        # Two-word keyword variants
        for kw in ('first strike', 'double strike'):
            if text in kw or text == kw:
                return True
        # Comma-separated bare-keyword form
        parts = [p.strip() for p in text.split(',') if p.strip()]
        if parts and all(p in KEYWORD_ONLY_TEXTS for p in parts):
            return True

    static_markers = (
        'other ',          # lord effects
        'creatures you control have',
        'have flying',
        'have trample',
        'have first strike',
        'have lifelink',
        'have vigilance',
        'have menace',
        'have haste',
        'have deathtouch',
        'have hexproof',
        'enchanted creature',
        'lose all abilities',  # Eraserhead-style query intercept
        'untargetable',
        'can\'t be',
    )
    return any(m in text for m in static_markers)


def is_creature(card_def) -> bool:
    chars = card_def.characteristics
    return CardType.CREATURE in (chars.types or set())


# =============================================================================
# Per-card runner
# =============================================================================

def run_card(card_name: str) -> tuple[str, str]:
    """Returns (status, detail). status in {'pass', 'fail', 'skip', 'error'}."""
    if card_name in SKIPPED_CARDS:
        return ('skip', SKIPPED_CARDS[card_name])

    card_def = MHA_CARDS[card_name]
    if not card_wires_setup(card_def):
        return ('skip', 'no setup_interceptors')

    # Skip non-creatures for this fast pass — instants/sorceries with
    # setup_interceptors are usually cast-effect dispatch, which needs
    # a different harness.
    if not is_creature(card_def):
        return ('skip', 'non-creature setup (cast-effect dispatch)')

    # Static-only lord effects don't emit events — categorize as skip,
    # not fail. They are still verified by registering without crashing.
    if card_is_static_only(card_def):
        try:
            game, p1, p2 = make_game()
            obj = create_card_on_battlefield(game, p1.id, card_name, fire_etb=False)
            # Manually run setup to verify it doesn't crash.
            itcs = card_def.setup_interceptors(obj, game.state)
            if itcs is None or (isinstance(itcs, list) and len(itcs) == 0):
                return ('fail', 'static lord setup returned no interceptors')
            return ('skip', 'static lord effect — registers interceptors, no event')
        except Exception as e:
            return ('error', f'{type(e).__name__}: {e}')

    # Standard wired creature path: drop on battlefield, watch events.
    try:
        game, p1, p2 = make_game()

        # Pre-populate enemy battlefield with a dummy creature so triggers
        # that scan opponent creatures (Bakugo "deal 1 dmg to each enemy
        # creature") have a target. Also pre-populate ally side so allies-
        # only triggers find a friend. Pre-populate hand so DRAW-style
        # effects have library access.
        for _ in range(2):
            game.create_object(
                name="DummyEnemy",
                owner_id=p2.id,
                zone=ZoneType.BATTLEFIELD,
                characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
                card_def=None,
            )
            game.create_object(
                name="DummyAlly",
                owner_id=p1.id,
                zone=ZoneType.BATTLEFIELD,
                characteristics=Characteristics(types={CardType.CREATURE}, power=1, toughness=1),
                card_def=None,
            )

        events_log = install_event_tracker(game)
        obj = create_card_on_battlefield(game, p1.id, card_name, fire_etb=True)
    except Exception as e:
        return ('error', f'setup: {type(e).__name__}: {e}')

    # Did anything effectful happen?
    effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
    if effectful:
        return ('pass', f'ETB emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    # ETB produced nothing. Try the attack trigger path (Slice-21 attack
    # patterns: drain on attack).
    try:
        fire_attack(game, obj)
    except Exception as e:
        return ('error', f'attack: {type(e).__name__}: {e}')

    effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
    if effectful:
        return ('pass', f'attack emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    # Last-ditch: death trigger.
    try:
        fire_death(game, obj)
    except Exception as e:
        return ('error', f'death: {type(e).__name__}: {e}')

    effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
    if effectful:
        return ('pass', f'death emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    return ('fail', 'empty_effect: ETB/attack/death produced no effectful event')


# =============================================================================
# Driver
# =============================================================================

def main():
    cards_in_scope = sorted(MHA_CARDS.keys())
    print(f"=== /test-interceptors :: custom/my_hero_academia ===")
    print(f"  total cards in dict: {len(cards_in_scope)}")

    results = {'pass': [], 'fail': [], 'skip': [], 'error': []}
    for name in cards_in_scope:
        try:
            status, detail = run_card(name)
        except Exception as e:
            status, detail = 'error', f'runner: {type(e).__name__}: {e}'
        results[status].append((name, detail))

    tested = len(results['pass']) + len(results['fail']) + len(results['error'])
    print(f"  tested:  {tested}")
    print(f"  passed:  {len(results['pass'])}")
    print(f"  failed:  {len(results['fail'])}")
    print(f"  errors:  {len(results['error'])}")
    print(f"  skipped: {len(results['skip'])}")

    pass_rate = (100.0 * len(results['pass']) / tested) if tested else 0.0
    print(f"  pass rate: {pass_rate:.1f}%")

    if results['fail']:
        print("\n--- FAILURES (first 25) ---")
        for name, detail in results['fail'][:25]:
            print(f"  FAIL {name}: {detail}")

    if results['error']:
        print("\n--- ERRORS (first 25) ---")
        for name, detail in results['error'][:25]:
            print(f"  ERR  {name}: {detail}")

    # Top broken hero list
    signature_heroes = [
        "Izuku Midoriya, One For All",
        "All Might, Symbol of Peace",
        "Katsuki Bakugo, Explosive Hero",
        "Endeavor, Number One Hero",
        "Shoto Todoroki, Half-Cold Half-Hot",
        "Ochaco Uraraka, Zero Gravity",
        "Tenya Iida, Engine Hero",
        "Eraserhead, Underground Hero",
        "Hawks, Number Two Hero",
        "All For One, Ultimate Villain",
        "Shigaraki, Decay Lord",
        "Mirio, Permeation Hero",
    ]
    bad_status = {s: d for s, d in results['fail']}
    bad_status.update({s: d for s, d in results['error']})
    broken_sigs = [(h, bad_status[h]) for h in signature_heroes if h in bad_status]
    if broken_sigs:
        print("\n--- BROKEN SIGNATURE HEROES ---")
        for n, d in broken_sigs:
            print(f"  {n}: {d}")

    # Bail with non-zero only on hard failures (errors). Empty-effect
    # cards are reported but not blocking — this matches the skill's
    # "warn-only" default for empty-effect.
    sys.exit(0 if not results['error'] else 1)


if __name__ == "__main__":
    main()
