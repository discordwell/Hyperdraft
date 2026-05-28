"""
Auto-generated interceptor verification for outlaws_thunder_junction (OTJ).

See `.claude/commands/test-interceptors.md`. This file dynamically iterates
every card in OUTLAWS_THUNDER_JUNCTION_CARDS that wires `setup_interceptors`,
drops it on the battlefield (firing the appropriate canonical trigger event
for its detected pattern), and asserts at least one non-empty event is
emitted.

OTJ mechanics covered:
  - Plot ({cost}, exile from hand; cast later as a sorcery for free)
  - Saddle N (tap creatures with total power N+ to saddle a Mount;
    "attacks while saddled" triggers)
  - Crime (target opponent / their permanent / their graveyard);
    "whenever you commit a crime" triggers
  - Spree (cost-per-mode modal spells)
  - Outlaw typal (Assassin / Mercenary / Pirate / Rogue / Warlock)

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
    InterceptorPriority,
)
from src.engine.game import Game
from src.cards.outlaws_thunder_junction import OUTLAWS_THUNDER_JUNCTION_CARDS as OTJ_CARDS


# Cards we cannot meaningfully auto-test — modal, target-choice, saga,
# replacement effects, equipment / aura statics that need an attached
# creature, or activated abilities that need a cost payment.
SKIPPED_CARDS = {
    # Pure modal / Spree (cost-per-mode) — needs choice resolution
    "Final Showdown": "Spree — modal cost-per-mode, needs mode chosen",
    "Getaway Glamer": "Spree — needs mode + target chosen",
    "Requisition Raid": "Spree — needs mode chosen",
    "Rustler Rampage": "Spree — needs mode + target chosen",
    "Take Up the Shield": "Spree — needs mode chosen",
    "Steer Clear": "Spree — needs mode chosen",
    "Another Round": "Spree — needs mode chosen",
    # Land statics & lands with abilities — no ETB trigger
    "Plains": "basic land",
    "Island": "basic land",
    "Swamp": "basic land",
    "Mountain": "basic land",
    "Forest": "basic land",
}


# =============================================================================
# Helpers (mirror tests/test_mha_interceptors.py)
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
        log.append(event)
        if isinstance(result, list):
            for e in result:
                if isinstance(e, Event):
                    log.append(e)
        return result

    game.emit = tracker
    return log


def create_card_on_battlefield(game, player_id, card_name, fire_etb=True):
    """Create the card in HAND then move to BATTLEFIELD via ZONE_CHANGE."""
    card_def = OTJ_CARDS[card_name]
    obj = game.create_object(
        name=card_name,
        owner_id=player_id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,
    )
    obj.card_def = card_def

    if fire_etb:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': obj.id,
                'from_zone_type': ZoneType.HAND,
                'to_zone_type': ZoneType.BATTLEFIELD,
            },
            source=obj.id,
            controller=obj.controller,
        ))
    return obj


def fire_attack(game, attacker):
    game.emit(Event(
        type=EventType.ATTACK_DECLARED,
        payload={'attacker_id': attacker.id, 'defending_player': 'opponent'},
        source=attacker.id,
        controller=attacker.controller,
    ))


def fire_death(game, obj):
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.GRAVEYARD,
        },
        source=obj.id,
        controller=obj.controller,
    ))


def fire_saddle_attack(game, mount_obj):
    """Saddle the Mount, then declare it as attacker.

    Mirrors the canonical Saddle path: ``saddled_until_eot`` flag plus
    ATTACK_DECLARED. Triggers wired via ``make_saddle_trigger`` only fire
    when the Mount is currently saddled.
    """
    # Mark as saddled (the trigger checks obj.state.saddled_until_eot).
    if hasattr(mount_obj, 'state'):
        mount_obj.state.saddled_until_eot = True
    # Also emit SADDLE_BECOMES_SADDLED so becomes_saddled triggers fire.
    game.emit(Event(
        type=EventType.SADDLE_BECOMES_SADDLED,
        payload={'mount_id': mount_obj.id},
        source=mount_obj.id,
        controller=mount_obj.controller,
    ))
    fire_attack(game, mount_obj)


def fire_crime(game, controller_id):
    """Emit a CRIME_COMMITTED event under controller_id.

    Crime is "target an opponent, anything they control, or a card in
    their graveyard." Cards with ``make_crime_committed_trigger`` listen
    for this event on their controller.
    """
    game.emit(Event(
        type=EventType.CRIME_COMMITTED,
        payload={'committer_id': controller_id, 'target_kind': 'opponent_creature'},
        source=controller_id,
        controller=controller_id,
    ))


def fire_becomes_plotted(game, obj):
    """Emit a PLOT_BECOMES_PLOTTED event for this card."""
    game.emit(Event(
        type=EventType.PLOT_BECOMES_PLOTTED,
        payload={'object_id': obj.id, 'controller_id': obj.controller},
        source=obj.id,
        controller=obj.controller,
    ))


# Event types we count as "real effects emitted by the card".
def _build_effectful_set():
    names = [
        'LIFE_CHANGE', 'DRAW', 'SCRY', 'DAMAGE', 'DISCARD',
        'SACRIFICE', 'OBJECT_DESTROYED', 'COUNTER_ADDED',
        'PT_MODIFICATION', 'CREATE_TOKEN', 'OBJECT_CREATED',
        'ACTIVATE', 'MILL', 'SURVEIL',
        'TAP', 'TAP_TARGET', 'UNTAP', 'UNTAP_TARGET',
        'REMOVE_ABILITIES', 'TEMPORARY_BOOST', 'TEMPORARY_PT_CHANGE',
        'EXILE', 'CONDITIONAL_COUNTERS',
        # OTJ-relevant — Plot/Saddle effects often surface via these
        'TOKEN_CREATED', 'TARGET_CHOSEN', 'CARD_DRAWN',
        # Treasure / Gold token markers (Plot deck staple)
        'TREASURE_CREATED', 'GOLD_CREATED',
    ]
    return {getattr(EventType, n) for n in names if hasattr(EventType, n)}


EFFECTFUL_EVENT_TYPES = _build_effectful_set()


KEYWORD_ONLY_TEXTS = {
    'flying', 'trample', 'haste', 'lifelink', 'vigilance', 'menace',
    'first strike', 'double strike', 'deathtouch', 'hexproof', 'reach',
    'defender', 'flash', 'indestructible', 'ward', 'protection',
}


def card_wires_setup(card_def) -> bool:
    return bool(getattr(card_def, 'setup_interceptors', None))


def card_text(card_def) -> str:
    return (getattr(card_def, 'text', '') or '').strip().lower()


def has_saddle(card_def) -> bool:
    """Mount cards with ``saddle N`` saddle-attack triggers."""
    text = card_text(card_def)
    return 'saddle' in text and 'whenever this creature attacks while saddled' in text


def has_crime_trigger(card_def) -> bool:
    text = card_text(card_def)
    return 'whenever you commit a crime' in text


def has_plot_becomes(card_def) -> bool:
    """Cards with 'When this card becomes plotted, <effect>'."""
    text = card_text(card_def)
    return 'becomes plotted' in text


def card_is_static_only(card_def) -> bool:
    """Static-only cards (lord effects, keyword grants, aura statics)
    register interceptors but emit no events on ETB."""
    text = card_text(card_def)

    if text:
        tokens = {t.strip(' .') for t in text.replace(',', ' ').split()}
        meaningful = {t for t in tokens if len(t) > 2}
        if meaningful and meaningful.issubset(KEYWORD_ONLY_TEXTS | {'and'}):
            return True
        for kw in ('first strike', 'double strike'):
            if text in kw or text == kw:
                return True
        parts = [p.strip() for p in text.split(',') if p.strip()]
        if parts and all(p in KEYWORD_ONLY_TEXTS for p in parts):
            return True

    static_markers = (
        'other creatures you control get',
        'creatures you control have',
        'creatures you control get',
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
        'equipped creature',
        'untargetable',
        "can't be",
    )
    return any(m in text for m in static_markers)


def is_creature(card_def) -> bool:
    chars = card_def.characteristics
    return CardType.CREATURE in (chars.types or set())


def is_enchantment_or_artifact_static(card_def) -> bool:
    """Auras / Equipment / static enchantments need an attached creature
    to surface effects; ETB usually no-ops."""
    chars = card_def.characteristics
    text = card_text(card_def)
    types = chars.types or set()
    if CardType.CREATURE in types:
        return False
    # Auras and equipments
    subtypes = chars.subtypes or set()
    if 'Aura' in subtypes or 'Equipment' in subtypes:
        return True
    # Pure enchantments / artifacts whose text describes ongoing state
    if (CardType.ENCHANTMENT in types or CardType.ARTIFACT in types):
        ongoing_markers = (
            "you can't lose the game", "players can't",
            'as long as', 'whenever a creature',
            'opponents can\'t', 'spells your opponents',
        )
        if any(m in text for m in ongoing_markers):
            return True
    return False


# =============================================================================
# Per-card runner
# =============================================================================

def run_card(card_name: str) -> tuple[str, str]:
    """Returns (status, detail). status in {'pass', 'fail', 'skip', 'error'}."""
    if card_name in SKIPPED_CARDS:
        return ('skip', SKIPPED_CARDS[card_name])

    card_def = OTJ_CARDS[card_name]
    if not card_wires_setup(card_def):
        return ('skip', 'no setup_interceptors')

    # Non-creatures with setup_interceptors are usually cast-effect dispatch
    # (instants / sorceries) — skip per the same convention used by other
    # interceptor smoke tests in this repo.
    if not is_creature(card_def):
        if is_enchantment_or_artifact_static(card_def):
            return ('skip', 'aura / equipment / ongoing static — no ETB emission')
        return ('skip', 'non-creature setup (cast-effect dispatch)')

    if card_is_static_only(card_def):
        try:
            game, p1, p2 = make_game()
            obj = create_card_on_battlefield(game, p1.id, card_name, fire_etb=False)
            itcs = card_def.setup_interceptors(obj, game.state)
            if itcs is None or (isinstance(itcs, list) and len(itcs) == 0):
                return ('fail', 'static lord setup returned no interceptors')
            return ('skip', 'static lord effect — registers interceptors, no event')
        except Exception as e:
            return ('error', f'{type(e).__name__}: {e}')

    # Standard wired creature path
    try:
        game, p1, p2 = make_game()

        # Pre-populate ally and opponent boards so triggers that scan find
        # targets (and so make_attached helpers don't choke on empty pools).
        for _ in range(2):
            game.create_object(
                name="DummyEnemy",
                owner_id=p2.id,
                zone=ZoneType.BATTLEFIELD,
                characteristics=Characteristics(
                    types={CardType.CREATURE},
                    subtypes={"Human"},
                    power=1, toughness=1,
                ),
                card_def=None,
            )
            game.create_object(
                name="DummyAlly",
                owner_id=p1.id,
                zone=ZoneType.BATTLEFIELD,
                characteristics=Characteristics(
                    types={CardType.CREATURE},
                    subtypes={"Human"},
                    power=1, toughness=1,
                ),
                card_def=None,
            )

        events_log = install_event_tracker(game)
        obj = create_card_on_battlefield(game, p1.id, card_name, fire_etb=True)
    except Exception as e:
        return ('error', f'setup: {type(e).__name__}: {e}')

    effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
    if effectful:
        return ('pass', f'ETB emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    # OTJ-specific trigger paths: Saddle, Crime, Plot-becomes.
    if has_saddle(card_def):
        try:
            fire_saddle_attack(game, obj)
        except Exception as e:
            return ('error', f'saddle: {type(e).__name__}: {e}')
        effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
        if effectful:
            return ('pass', f'saddle-attack emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    if has_crime_trigger(card_def):
        try:
            fire_crime(game, p1.id)
        except Exception as e:
            return ('error', f'crime: {type(e).__name__}: {e}')
        effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
        if effectful:
            return ('pass', f'crime emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    if has_plot_becomes(card_def):
        try:
            fire_becomes_plotted(game, obj)
        except Exception as e:
            return ('error', f'plot: {type(e).__name__}: {e}')
        effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
        if effectful:
            return ('pass', f'plot emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    # Attack path (generic).
    try:
        fire_attack(game, obj)
    except Exception as e:
        return ('error', f'attack: {type(e).__name__}: {e}')

    effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
    if effectful:
        return ('pass', f'attack emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    # Death.
    try:
        fire_death(game, obj)
    except Exception as e:
        return ('error', f'death: {type(e).__name__}: {e}')

    effectful = [e for e in events_log if e.type in EFFECTFUL_EVENT_TYPES]
    if effectful:
        return ('pass', f'death emitted {len(effectful)} effects (e.g. {effectful[0].type.name})')

    return ('fail', 'empty_effect: ETB/saddle/crime/plot/attack/death produced no effectful event')


# =============================================================================
# Driver
# =============================================================================

def main():
    cards_in_scope = sorted(OTJ_CARDS.keys())
    print(f"=== /test-interceptors :: outlaws_thunder_junction (OTJ) ===")
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

    # OTJ-specific mechanic gap diagnostics
    print("\n--- OTJ MECHANIC BREAKDOWN ---")
    saddle_fail = [n for n, d in results['fail'] if has_saddle(OTJ_CARDS[n])]
    crime_fail = [n for n, d in results['fail'] if has_crime_trigger(OTJ_CARDS[n])]
    plot_fail = [n for n, d in results['fail'] if has_plot_becomes(OTJ_CARDS[n])]
    print(f"  Saddle cards failing: {len(saddle_fail)}")
    print(f"  Crime trigger cards failing: {len(crime_fail)}")
    print(f"  Plot-becomes cards failing: {len(plot_fail)}")

    # Bail with non-zero only on hard errors. Empty-effect failures are
    # reported but not blocking.
    sys.exit(0 if not results['error'] else 1)


if __name__ == "__main__":
    main()
