"""Regression: the depth metric cannot be gamed by text-mismatched info-pulse events.

Pins the anti-gaming text-match guard added to `src/depth/axis_scorer.py` after
the "slice-N median-lift / spice-pass" incident, in which auto-generated
`_<set>_s<N>_*` stub helpers wired hundreds of cards to emit generic
SCRY/SURVEIL/MILL/LIFE_CHANGE "info-pulse" events REGARDLESS of each card's
printed rules text, purely to inflate `depth_v2_median`. The scorer credited
those events on the Asymmetry axis because it only inspected what a card's
effect_fn *emits* and never compared against what its text *says*.

This file makes that exploit falsifiable in both directions:

  1. STUB (text says "deal damage", emits SCRY) → Asymmetry credit REVOKED.
  2. HONEST (text says "scry", emits SCRY)      → Asymmetry credit KEPT.
  3. Pokemon attack rules-text (in `attacks[].text`, not flavor `text`) is
     read by the guard, so a real "Look at your opponent's hand" attack still
     scores asymmetry.
  4. Empty-text fixtures fall through unchanged (no false negatives) — this is
     what keeps the scorer-calibration fixtures in test_axis_scorer_helpers.py
     green.

Run:
    PYTHONPATH=. python tests/test_depth_anti_gaming.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Worktree-portable sys.path (gotcha #18 in spice-pass.md): never hardcode the
# main checkout path — compute repo root from __file__.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.engine import (  # noqa: E402
    Color, Event, EventType, GameObject, GameState, Interceptor, make_creature,
)
from src.cards import interceptor_helpers as ih  # noqa: E402
from src.depth import get_profile, score_card  # noqa: E402
from src.depth.axis_scorer import (  # noqa: E402
    _card_rules_text,
    _text_corroborates_event,
)


# ---------------------------------------------------------------------------
# Module-level card defs (the AST walker needs readable source on disk, so the
# effect closures must live at module scope, not inside a test body).
# ---------------------------------------------------------------------------


def _stub_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Emit a generic SCRY info-pulse on ETB — the exact shape the slice-N
    stubs used. The effect closure is nested so the AST walker's closure-cell
    walk surfaces the EventType.SCRY (matching the working fixture pattern in
    test_axis_scorer_helpers.py)."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY,
                      payload={"player": obj.controller, "amount": 2},
                      source=obj.id)]
    return [ih.make_etb_trigger(obj, effect_fn)]


# Text says "deal 3 damage"; effect emits SCRY. Classic median-lift stub.
_STUB_CARD = make_creature(
    name="Test Stub Burner",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="When Test Stub Burner enters the battlefield, it deals 3 damage to any target.",
    setup_interceptors=_stub_setup,
)

# Text actually says "scry"; effect emits SCRY. Legitimate.
_HONEST_CARD = make_creature(
    name="Test Honest Seer",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="When Test Honest Seer enters the battlefield, scry 2.",
    setup_interceptors=_stub_setup,  # same effect closure; only the text differs
)

# No printed text at all — must fall through unchanged (no false negative).
_NOTEXT_CARD = make_creature(
    name="Test Textless Seer",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    setup_interceptors=_stub_setup,
)


def test_stub_emitting_scry_with_unrelated_text_gets_no_asymmetry():
    """The core anti-gaming guard: a card whose text describes damage but whose
    effect_fn emits SCRY must NOT receive Asymmetry credit for the SCRY. This is
    the structural defense that makes the slice-N median-lift exploit impossible."""
    mtg = get_profile("mtg")
    cs = score_card(_STUB_CARD, mtg)
    assert "SCRY" in cs.features.event_types, (
        "Sanity: the AST walker must still SEE the emitted SCRY (the "
        "FeatureBag / code-fingerprint is intentionally left intact); "
        f"got event_types={sorted(cs.features.event_types)}"
    )
    assert cs.scores.asymmetry == 0, (
        f"Stub SCRY (text says 'deal damage', no scry) must yield asymmetry=0; "
        f"got A={cs.scores.asymmetry}, axes={cs.scores.fingerprint}. "
        f"The depth metric is gameable if this fails."
    )


def test_honest_scry_card_keeps_asymmetry_credit():
    """A card whose printed text actually says 'scry' keeps full info-asymmetry
    credit — the guard must not punish legitimate effects."""
    mtg = get_profile("mtg")
    cs = score_card(_HONEST_CARD, mtg)
    assert cs.scores.asymmetry == 3, (
        f"Honest scry card (text says 'scry 2') should score asymmetry=3 "
        f"(information event); got A={cs.scores.asymmetry}, axes={cs.scores.fingerprint}"
    )


def test_textless_card_falls_through_unchanged():
    """A card with no printed text can't be judged, so the guard must not strip
    its events — this preserves the scorer-calibration fixtures and avoids any
    false negative on genuinely text-less tokens."""
    mtg = get_profile("mtg")
    cs = score_card(_NOTEXT_CARD, mtg)
    assert cs.scores.asymmetry == 3, (
        f"Textless SCRY card should keep asymmetry=3 (legacy fall-through); "
        f"got A={cs.scores.asymmetry}"
    )


def test_guard_reads_pokemon_attack_rules_text_not_just_flavor():
    """For Pokemon, rules text lives in `attacks[].text`, not the flavor `text`
    field. The guard must read the attack text so a real 'Look at your
    opponent's hand' attack (emitting PKM_REVEAL) keeps its asymmetry credit.
    Regression for the false-strip that dropped Jace, Memory Adept and Mirko
    Vosk during development of this guard."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    pkm = get_profile("pokemon")
    for name in ("Jace, Memory Adept", "Mirko Vosk, Mind Drinker"):
        cd = BEYOND_RAVNICA_CARDS[name]
        cs = score_card(cd, pkm)
        assert cs.scores.asymmetry >= 1, (
            f"{name} reveals opponent info in its attack text but scored "
            f"asymmetry={cs.scores.asymmetry} — the guard is reading flavor "
            f"text instead of attack rules text."
        )


def test_rules_text_blob_includes_attacks_and_ability():
    """`_card_rules_text` must concatenate attack/ability text, not just flavor."""
    from src.cards.pokemon.beyond.ravnica import BEYOND_RAVNICA_CARDS
    cd = BEYOND_RAVNICA_CARDS["Jace, Memory Adept"]
    blob = _card_rules_text(cd).lower()
    assert "look at" in blob, (
        f"rules-text blob should include the attack text; got: {blob[:120]!r}"
    )


def test_text_corroborates_event_semantics():
    """Unit-level checks on the corroboration predicate."""
    # Matching keyword present → corroborated.
    assert _text_corroborates_event("Scry 2, then draw a card.", "SCRY")
    # Keyword absent in substantive text → NOT corroborated (strip).
    assert not _text_corroborates_event("Deal 3 damage to any target.", "SCRY")
    # Empty text → corroborated (fall through, no false negative).
    assert _text_corroborates_event("", "SCRY")
    # Event with no vocabulary entry → corroborated (we only gate known events).
    assert _text_corroborates_event("Deal 3 damage.", "SOME_UNGATED_EVENT")


if __name__ == "__main__":
    tests = [
        test_stub_emitting_scry_with_unrelated_text_gets_no_asymmetry,
        test_honest_scry_card_keeps_asymmetry_credit,
        test_textless_card_falls_through_unchanged,
        test_guard_reads_pokemon_attack_rules_text_not_just_flavor,
        test_rules_text_blob_includes_attacks_and_ability,
        test_text_corroborates_event_semantics,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {t.__name__}: {e!r}")
            failed += 1
    print(f"\n{passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
