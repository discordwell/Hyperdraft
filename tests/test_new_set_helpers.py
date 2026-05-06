"""
Unit tests for scripts/new_set/ helpers.

Run directly:
    python tests/test_new_set_helpers.py
or via pytest:
    python -m pytest tests/test_new_set_helpers.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.new_set.coverage import (         # noqa: E402
    parse_card_ref,
    stats_for_set,
    domain_matches_set,
    analyze_coverage,
    build_force_include_spec,
    force_include_specs_for_zero_plays,
)
from scripts.new_set.balance_loop import (     # noqa: E402
    compute_card_flags,
    compute_archetype_flags,
    analyze_round,
    should_continue_loop,
    Z_FLAG_THRESHOLD,
    MIN_IN_PLAY_SAMPLES,
    LOW_WINRATE,
    HIGH_WINRATE,
    DEFAULT_MAX_CYCLES,
)
from scripts.new_set import wire_set            # noqa: E402
from scripts.new_set.art_harness import (       # noqa: E402
    build_prompt,
    to_filename,
    load_style,
    StyleConfig,
)


# =============================================================================
# coverage.py
# =============================================================================

def test_parse_card_ref_ok():
    assert parse_card_ref("MYSET::Lightning Bolt") == ("MYSET", "Lightning Bolt")


def test_parse_card_ref_malformed():
    assert parse_card_ref("MYSET-Lightning Bolt") is None
    assert parse_card_ref("just_a_name") is None


def test_stats_for_set_filters_by_domain():
    scores = {
        "MYSET::Card A": {"cast": 3},
        "OTHER::Card A": {"cast": 5},
        "MYSET::Card B": {"cast": 1},
    }
    out = stats_for_set(scores, "MYSET")
    assert set(out.keys()) == {"Card A", "Card B"}
    assert out["Card A"]["cast"] == 3


def test_domain_matches_set_exact_and_prefix():
    # Exact match (single mirror pool)
    assert domain_matches_set("PIRT", "PIRT")
    # Archetype prefix (per-archetype tournament pools)
    assert domain_matches_set("PIRT_aggro", "PIRT")
    assert domain_matches_set("PIRT_control", "PIRT")
    # Different sets that happen to share a prefix MUST NOT match
    assert not domain_matches_set("PIRTANIA", "PIRT")
    assert not domain_matches_set("PIRTX", "PIRT")
    # Other unrelated domains
    assert not domain_matches_set("OTHER", "PIRT")
    assert not domain_matches_set("OTHER_aggro", "PIRT")


def test_stats_for_set_sums_across_archetype_prefixes():
    """Tournament uses deck-pool labels as `::` prefix, so a single card
    appearing in two archetype decks shows up under two keys. The filter
    must sum those entries and re-derive rates from the summed counters."""
    scores = {
        "PIRT_aggro::Captain": {
            "cast": 10, "deck_copies": 8, "in_play_at_end": 5,
            "on_winning_side": 4, "cast_per_copy": 1.25, "win_rate_in_play": 0.8,
        },
        "PIRT_control::Captain": {
            "cast": 2, "deck_copies": 8, "in_play_at_end": 1,
            "on_winning_side": 1, "cast_per_copy": 0.25, "win_rate_in_play": 1.0,
        },
        "OTHER::Captain": {  # different set — must be excluded
            "cast": 100, "deck_copies": 4, "in_play_at_end": 50,
            "on_winning_side": 50, "cast_per_copy": 25.0, "win_rate_in_play": 1.0,
        },
    }
    out = stats_for_set(scores, "PIRT")
    assert set(out.keys()) == {"Captain"}
    cap = out["Captain"]
    # Counters summed
    assert cap["cast"] == 12
    assert cap["deck_copies"] == 16
    assert cap["in_play_at_end"] == 6
    assert cap["on_winning_side"] == 5
    # Rates RE-DERIVED from summed counters, not naively summed
    assert cap["cast_per_copy"] == round(12 / 16, 3)
    assert cap["win_rate_in_play"] == round(5 / 6, 3)


def test_stats_for_set_does_not_clobber_single_entry_rates():
    """Single-entry cards keep their upstream-aggregator rates as-is —
    no spurious zero-rate from rederivation."""
    scores = {
        "PIRT_aggro::Solo": {
            "cast": 10, "deck_copies": 4, "in_play_at_end": 5,
            "win_rate_in_play": 0.99,    # no on_winning_side key!
        },
    }
    out = stats_for_set(scores, "PIRT")
    assert out["Solo"]["win_rate_in_play"] == 0.99   # preserved


def test_analyze_coverage_zero_plays():
    tournament = {
        "card_scores": {
            "MYSET::A": {"cast": 5, "cast_per_copy": 0.5, "in_play_at_end": 2},
            "MYSET::B": {"cast": 0, "cast_per_copy": 0.0, "in_play_at_end": 0},
            "MYSET::C": {"cast": 3, "cast_per_copy": 0.04, "in_play_at_end": 1},
        }
    }
    report = analyze_coverage(tournament, "MYSET")
    assert "B" in report.cards_with_zero_plays
    assert "C" in report.cards_with_low_play_rate
    assert "A" not in report.cards_with_zero_plays
    assert report.total_cards == 3


def test_analyze_coverage_never_in_deck():
    tournament = {"card_scores": {"MYSET::A": {"cast": 1}}}
    report = analyze_coverage(tournament, "MYSET", card_list=["A", "B", "C"])
    assert report.cards_never_in_deck == ["B", "C"]
    assert report.total_cards == 3
    # A counted (played); B & C are never_in_deck — coverage = 1/3
    assert abs(report.coverage_pct - (1 / 3)) < 0.001


def test_analyze_coverage_dedupes_card_list():
    """Bug #6 from code review — duplicates in card_list must not
    inflate the denominator or produce duplicate never_in_deck entries."""
    tournament = {"card_scores": {"MYSET::A": {"cast": 1}}}
    # B appears twice, A appears twice
    report = analyze_coverage(tournament, "MYSET", card_list=["A", "A", "B", "B", "C"])
    # Unique cards = 3 (A, B, C); A is played → 1 played, 2 never-in-deck
    assert report.total_cards == 3
    assert report.cards_never_in_deck == ["B", "C"]
    assert abs(report.coverage_pct - (1 / 3)) < 0.001


def test_build_force_include_spec_basic():
    deck = build_force_include_spec("Target", ["X", "Y", "Z"], deck_size=10, copies_of_target=4)
    assert len(deck) == 10
    assert deck.count("Target") == 4
    # filler is a round-robin of base cards
    assert deck[4:] == ["X", "Y", "Z", "X", "Y", "Z"]


def test_build_force_include_spec_no_filler_pads_with_target():
    deck = build_force_include_spec("Target", [], deck_size=5, copies_of_target=2)
    assert deck.count("Target") == 5


def test_build_force_include_spec_copies_eq_deck_size():
    deck = build_force_include_spec("T", ["X"], deck_size=4, copies_of_target=4)
    assert deck == ["T", "T", "T", "T"]


def test_force_include_specs_for_zero_plays_emits_one_per_card():
    tournament = {"card_scores": {
        "MYSET::A": {"cast": 5, "cast_per_copy": 0.5, "in_play_at_end": 2},
        "MYSET::B": {"cast": 0, "cast_per_copy": 0.0, "in_play_at_end": 0},
        "MYSET::C": {"cast": 0, "cast_per_copy": 0.0, "in_play_at_end": 0},
    }}
    report = analyze_coverage(tournament, "MYSET")
    specs = force_include_specs_for_zero_plays(report, ["filler"], deck_size=20, copies_of_target=4)
    assert set(specs.keys()) == {"B", "C"}
    for name, deck in specs.items():
        assert len(deck) == 20
        assert deck.count(name) == 4


# =============================================================================
# balance_loop.py
# =============================================================================

def _scores_with_winrates(rates: list[float], in_play: int = 10) -> dict:
    """Build a card_scores dict where each entry has the given win_rate_in_play."""
    return {
        f"MYSET::card_{i}": {
            "win_rate_in_play": r,
            "in_play_at_end": in_play,
            "cast": 5,
            "deck_copies": 4,
        }
        for i, r in enumerate(rates)
    }


def test_compute_card_flags_overpowered():
    # 4 cards near 0.5, 1 card at 0.95 → that one is the outlier.
    scores = _scores_with_winrates([0.5, 0.5, 0.5, 0.5, 0.95])
    flags, median, excluded = compute_card_flags(scores, "MYSET", min_samples=2)
    op = [f for f in flags if f.direction == "overpowered"]
    assert len(op) == 1
    assert op[0].name == "card_4"
    assert op[0].z_score >= Z_FLAG_THRESHOLD


def test_compute_card_flags_underpowered():
    scores = _scores_with_winrates([0.5, 0.5, 0.5, 0.5, 0.05])
    flags, _, _ = compute_card_flags(scores, "MYSET", min_samples=2)
    up = [f for f in flags if f.direction == "underpowered"]
    assert len(up) == 1
    assert up[0].name == "card_4"


def test_compute_card_flags_low_sample_advisory_only():
    scores = {
        "MYSET::A": {"win_rate_in_play": 0.99, "in_play_at_end": 1, "cast": 1, "deck_copies": 4},
        "MYSET::B": {"win_rate_in_play": 0.5,  "in_play_at_end": 20, "cast": 5, "deck_copies": 4},
        "MYSET::C": {"win_rate_in_play": 0.5,  "in_play_at_end": 20, "cast": 5, "deck_copies": 4},
        "MYSET::D": {"win_rate_in_play": 0.5,  "in_play_at_end": 20, "cast": 5, "deck_copies": 4},
        "MYSET::E": {"win_rate_in_play": 0.5,  "in_play_at_end": 20, "cast": 5, "deck_copies": 4},
    }
    flags, _, excluded = compute_card_flags(scores, "MYSET", min_samples=5)
    # A is low-sample → advisory only (won't trigger overpowered despite 0.99)
    a_flag = [f for f in flags if f.name == "A"][0]
    assert a_flag.direction == "low_sample"
    assert excluded == 1
    # B-E should not be flagged (all near baseline)
    assert all(f.direction != "overpowered" for f in flags)


def test_compute_card_flags_all_low_sample():
    scores = _scores_with_winrates([0.5, 0.99, 0.01], in_play=1)
    flags, median, excluded = compute_card_flags(scores, "MYSET", min_samples=5)
    assert excluded == 3
    assert all(f.direction == "low_sample" for f in flags)
    assert median == 0.0


def test_compute_archetype_flags_below_floor():
    summary = {
        "MYSET_aggro":   {"winrate": 0.30, "games_played": 100},
        "MYSET_control": {"winrate": 0.50, "games_played": 100},
    }
    flags = compute_archetype_flags(summary, ["MYSET_aggro", "MYSET_control"])
    assert len(flags) == 1
    assert flags[0].domain == "MYSET_aggro"
    assert flags[0].direction == "underpowered"


def test_compute_archetype_flags_above_ceiling():
    summary = {"MYSET_combo": {"winrate": 0.75, "games_played": 50}}
    flags = compute_archetype_flags(summary, ["MYSET_combo"])
    assert len(flags) == 1
    assert flags[0].direction == "overpowered"


def test_compute_archetype_flags_below_min_games_skipped():
    summary = {"MYSET_aggro": {"winrate": 0.20, "games_played": 5}}
    flags = compute_archetype_flags(summary, ["MYSET_aggro"], min_games=10)
    assert flags == []


def test_analyze_round_converged_when_no_flags():
    tournament = {
        "set_summary": {"MYSET_a": {"winrate": 0.5, "games_played": 50}},
        "card_scores": _scores_with_winrates([0.5] * 5, in_play=10),
    }
    report = analyze_round(tournament, "MYSET", ["MYSET_a"], cycle=1, min_samples=5)
    assert report.converged is True
    assert not should_continue_loop(report)


def test_analyze_round_continues_when_flagged():
    tournament = {
        "set_summary": {"MYSET_a": {"winrate": 0.50, "games_played": 50}},
        "card_scores": _scores_with_winrates([0.5, 0.5, 0.5, 0.5, 0.99], in_play=10),
    }
    report = analyze_round(tournament, "MYSET", ["MYSET_a"], cycle=1, min_samples=5)
    assert report.converged is False
    assert should_continue_loop(report) is True


def test_should_continue_loop_max_cycles():
    tournament = {
        "set_summary": {"MYSET_a": {"winrate": 0.10, "games_played": 50}},
        "card_scores": _scores_with_winrates([0.5] * 5, in_play=10),
    }
    report = analyze_round(tournament, "MYSET", ["MYSET_a"], cycle=10, min_samples=5)
    assert should_continue_loop(report, max_cycles=10) is False


def test_analyze_round_empty_card_scores_does_not_falsely_converge():
    """Bug #2 from code review — a tournament that errored out and
    returned no card data must NOT report converged=True."""
    tournament = {"set_summary": {}, "card_scores": {}}
    report = analyze_round(tournament, "MYSET", [], cycle=1)
    assert report.converged is False
    assert report.error and "card_scores" in report.error
    # Loop must continue (or, in practice, the orchestrator must surface
    # the error and halt the pipeline).
    assert should_continue_loop(report) is True


def test_analyze_round_no_matching_set_does_not_falsely_converge():
    """Cards exist but none match the set_label (e.g. wrong deck-label
    convention) — must report not-converged with explicit error."""
    tournament = {
        "set_summary": {"OTHER_a": {"winrate": 0.5, "games_played": 50}},
        "card_scores": {
            "OTHER::C": {"win_rate_in_play": 0.5, "in_play_at_end": 10,
                         "cast": 5, "deck_copies": 4},
        },
    }
    report = analyze_round(tournament, "PIRT", ["PIRT_aggro"], cycle=1)
    assert report.converged is False
    assert report.error and "PIRT" in report.error
    assert report.cards_analyzed == 0


def test_analyze_round_includes_cards_analyzed_count():
    tournament = {
        "set_summary": {"MYSET_a": {"winrate": 0.5, "games_played": 50}},
        "card_scores": _scores_with_winrates([0.5] * 5, in_play=10),
    }
    # The fixture uses MYSET::card_N (exact match), all 5 should be analyzed
    report = analyze_round(tournament, "MYSET", ["MYSET_a"], cycle=1, min_samples=5)
    assert report.cards_analyzed == 5


# =============================================================================
# wire_set.py
# =============================================================================

# Minimal copy of set_registry.py shape — exercises the regex anchors.
_FAKE_REGISTRY = textwrap.dedent('''
    """fake module."""
    from . import (
        ALPHA_CARDS,
    )
    from .custom import (
        BETA_CARDS,
    )

    SETS: dict[str, SetInfo] = {
        "ALPHA": SetInfo("ALPHA", "Alpha", len(ALPHA_CARDS), "2020-01-01", "standard"),
        "BETA": SetInfo("BETA", "Beta", len(BETA_CARDS), "2020-02-01", "custom"),
    }

    SET_REGISTRIES: list[tuple[str, dict]] = [
        ("ALPHA", ALPHA_CARDS),
        ("BETA", BETA_CARDS),
    ]
''').lstrip()

_FAKE_CUSTOM_INIT = textwrap.dedent('''
    """fake custom init."""
    from .beta import BETA_CARDS
''').lstrip()


def test_register_mtg_set_appends_all_three_locations(tmp_path: Path = None):
    tmp = tmp_path or Path(tempfile.mkdtemp())
    cards_dir = tmp / "src" / "cards"
    custom_dir = cards_dir / "custom"
    custom_dir.mkdir(parents=True)
    (cards_dir / "set_registry.py").write_text(_FAKE_REGISTRY, encoding="utf-8")
    (custom_dir / "__init__.py").write_text(_FAKE_CUSTOM_INIT, encoding="utf-8")

    # Patch the module-level constants for this test.
    saved_root = wire_set.PROJECT_ROOT
    saved_reg = wire_set.SET_REGISTRY_PATH
    saved_init = wire_set.CUSTOM_INIT_PATH
    try:
        wire_set.PROJECT_ROOT = tmp
        wire_set.SET_REGISTRY_PATH = cards_dir / "set_registry.py"
        wire_set.CUSTOM_INIT_PATH = custom_dir / "__init__.py"

        wire_set.register_mtg_set(
            code="MYSET", name="My Set", module="myset",
            registry_var="MYSET_CARDS", set_type="custom",
            release_date="2026-01-01", custom=True,
        )
        registry_text = (cards_dir / "set_registry.py").read_text()
        init_text = (custom_dir / "__init__.py").read_text()

        assert "MYSET_CARDS," in registry_text
        assert '"MYSET": SetInfo("MYSET", "My Set", len(MYSET_CARDS)' in registry_text
        assert '("MYSET", MYSET_CARDS),' in registry_text
        assert "from .myset import MYSET_CARDS" in init_text

        # Idempotent: second run no-ops.
        before = registry_text
        wire_set.register_mtg_set(
            code="MYSET", name="My Set", module="myset",
            registry_var="MYSET_CARDS", set_type="custom",
            release_date="2026-01-01", custom=True,
        )
        assert (cards_dir / "set_registry.py").read_text() == before
    finally:
        wire_set.PROJECT_ROOT = saved_root
        wire_set.SET_REGISTRY_PATH = saved_reg
        wire_set.CUSTOM_INIT_PATH = saved_init


_FAKE_ENGINE_INIT = textwrap.dedent('''
    """fake engine."""
    from .alpha import ALPHA_CARDS
    from .beta import BETA_CARDS

    MINECRAFT_CARDS: dict = {**ALPHA_CARDS, **BETA_CARDS}
''').lstrip()


_FAKE_ENGINE_INIT_WITH_LEGACY = textwrap.dedent('''
    """fake engine with a legacy alias dict that should NOT be matched."""
    from .alpha import ALPHA_CARDS

    MINECRAFT_CARDS_LEGACY: dict = {**ALPHA_CARDS}
    MINECRAFT_CARDS: dict = {**ALPHA_CARDS}
''').lstrip()


def test_register_engine_set_does_not_match_prefix_var(tmp_path: Path = None):
    """Bug #4 from code review — a file with both MINECRAFT_CARDS_LEGACY
    and MINECRAFT_CARDS must only have the latter modified when targeting
    MINECRAFT_CARDS."""
    tmp = tmp_path or Path(tempfile.mkdtemp())
    engine_dir = tmp / "src" / "cards" / "minecraft"
    engine_dir.mkdir(parents=True)
    (engine_dir / "__init__.py").write_text(
        _FAKE_ENGINE_INIT_WITH_LEGACY, encoding="utf-8"
    )

    saved_root = wire_set.PROJECT_ROOT
    try:
        wire_set.PROJECT_ROOT = tmp
        wire_set.register_engine_set(
            engine="minecraft", module="myset",
            registry_var="MYSET_CARDS", aggregate_var="MINECRAFT_CARDS",
        )
        text = (engine_dir / "__init__.py").read_text()
        # The TARGETED dict got the spread inserted
        target_line = [l for l in text.splitlines() if l.startswith("MINECRAFT_CARDS:")][0]
        assert "**MYSET_CARDS" in target_line
        # The LEGACY dict stayed untouched
        legacy_line = [l for l in text.splitlines() if l.startswith("MINECRAFT_CARDS_LEGACY:")][0]
        assert "**MYSET_CARDS" not in legacy_line
    finally:
        wire_set.PROJECT_ROOT = saved_root


def test_register_engine_set_merges_aggregate(tmp_path: Path = None):
    tmp = tmp_path or Path(tempfile.mkdtemp())
    engine_dir = tmp / "src" / "cards" / "minecraft"
    engine_dir.mkdir(parents=True)
    (engine_dir / "__init__.py").write_text(_FAKE_ENGINE_INIT, encoding="utf-8")

    saved_root = wire_set.PROJECT_ROOT
    try:
        wire_set.PROJECT_ROOT = tmp
        wire_set.register_engine_set(
            engine="minecraft",
            module="myset",
            registry_var="MYSET_CARDS",
            aggregate_var="MINECRAFT_CARDS",
        )
        text = (engine_dir / "__init__.py").read_text()
        assert "from .myset import MYSET_CARDS" in text
        assert "**MYSET_CARDS" in text
        # ALPHA and BETA still present
        assert "**ALPHA_CARDS" in text
        assert "**BETA_CARDS" in text
        # Idempotent
        before = text
        wire_set.register_engine_set(
            engine="minecraft", module="myset",
            registry_var="MYSET_CARDS", aggregate_var="MINECRAFT_CARDS",
        )
        assert (engine_dir / "__init__.py").read_text() == before
    finally:
        wire_set.PROJECT_ROOT = saved_root


def test_scaffold_smoke_test_valid_python(tmp_path: Path = None):
    tmp = tmp_path or Path(tempfile.mkdtemp())
    out = tmp / "test_myset.py"
    wire_set.scaffold_smoke_test(
        set_label="MYSET",
        import_path="src.cards.minecraft.myset",
        registry_var="MYSET_CARDS",
        decks=[("aggro", "make_aggro_deck"), ("control", "make_control_deck")],
        out_path=out,
    )
    text = out.read_text()
    # Compiles as Python
    compile(text, str(out), "exec")
    assert "test_every_card_loads" in text
    assert "test_deck_aggro_builds" in text
    assert "test_deck_control_builds" in text
    assert "from src.cards.minecraft.myset import MYSET_CARDS" in text


def test_scaffold_smoke_test_no_decks(tmp_path: Path = None):
    tmp = tmp_path or Path(tempfile.mkdtemp())
    out = tmp / "test_x.py"
    wire_set.scaffold_smoke_test(
        set_label="X", import_path="x.y", registry_var="X_CARDS", decks=[], out_path=out,
    )
    text = out.read_text()
    compile(text, str(out), "exec")
    assert "test_deck_" not in text


# =============================================================================
# art_harness.py
# =============================================================================

class _FakeChars:
    def __init__(self, types):
        self.types = types


class _FakeCard:
    def __init__(self, name, types=None, text=""):
        self.name = name
        self.text = text
        self.characteristics = _FakeChars(types or set())


def test_to_filename_normalizes():
    assert to_filename("Lightning Bolt!") == "lightning_bolt"
    assert to_filename("Mr. Smith's Dog (foo)") == "mr_smiths_dog_foo"


def test_build_prompt_with_text():
    style = StyleConfig(
        style_headline="STYLE.",
        category_flavors={"creature": "FLAVOR_C", "object": "FLAVOR_O"},
        categorize=lambda c: "creature",
    )
    card = _FakeCard("Lightning Bolt", text="Deal 3 damage to any target.")
    p = build_prompt(card, style)
    assert p.startswith("STYLE.")
    assert "Card name: Lightning Bolt." in p
    assert "FLAVOR_C" in p
    assert "Card flavor / behavior cue: Deal 3 damage to any target." in p


def test_build_prompt_truncates_long_text():
    style = StyleConfig(
        style_headline="X", category_flavors={"object": "Y"},
        categorize=lambda c: "object",
    )
    card = _FakeCard("Wordy", text="A " * 200)
    p = build_prompt(card, style)
    # Long flavor truncated to 240 chars + ellipsis
    assert "..." in p


def test_build_prompt_falls_back_to_object_when_category_missing():
    style = StyleConfig(
        style_headline="X", category_flavors={"object": "Y"},
        categorize=lambda c: "nonexistent",
    )
    card = _FakeCard("X")
    p = build_prompt(card, style)
    assert "Y" in p


def test_load_style_validates_module(tmp_path: Path = None):
    tmp = tmp_path or Path(tempfile.mkdtemp())
    mod = tmp / "fake_style_mod.py"
    mod.write_text(textwrap.dedent('''
        STYLE_HEADLINE = "headline"
        CATEGORY_FLAVORS = {"creature": "C", "object": "O"}
    ''').lstrip())
    sys.path.insert(0, str(tmp))
    try:
        style = load_style("fake_style_mod")
        assert style.style_headline == "headline"
        assert style.category_flavors == {"creature": "C", "object": "O"}
        # default categorize fn returns "object" for an empty card
        assert style.categorize(_FakeCard("x")) == "object"
    finally:
        sys.path.remove(str(tmp))


def test_load_style_rejects_missing_headline(tmp_path: Path = None):
    tmp = tmp_path or Path(tempfile.mkdtemp())
    mod = tmp / "bad_style_mod.py"
    mod.write_text("CATEGORY_FLAVORS = {'object': 'O'}\n")
    sys.path.insert(0, str(tmp))
    try:
        try:
            load_style("bad_style_mod")
        except ValueError as e:
            assert "STYLE_HEADLINE" in str(e)
        else:
            raise AssertionError("expected ValueError")
    finally:
        sys.path.remove(str(tmp))


# =============================================================================
# Driver
# =============================================================================

def _run_all():
    """For direct invocation — pytest discovers tests automatically."""
    import inspect
    fns = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]
    failed: list[tuple[str, BaseException]] = []
    for name, fn in fns:
        sig = inspect.signature(fn)
        kwargs = {}
        if "tmp_path" in sig.parameters:
            kwargs["tmp_path"] = Path(tempfile.mkdtemp())
        try:
            fn(**kwargs)
            print(f"  PASS  {name}")
        except BaseException as exc:
            print(f"  FAIL  {name}: {exc}")
            failed.append((name, exc))
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_all()
