from scripts.play.custom_set_depth_report import (
    build_report,
    card_depth,
    summarize_set,
)
from scripts.play.compare_custom_set_depth_reports import compare_reports


class _TinyCard:
    name = "Tiny"
    text = "Flying"
    abilities = []
    attacks = []
    setup_interceptors = None
    setup_in_graveyard = None
    setup_in_hand = None
    battlecry = None
    deathrattle = None
    spell_effect = None
    ability = None


class _DeepCard:
    name = "Deep"
    text = "Whenever you cast a spell, draw a card, then discard a card."
    abilities = []
    attacks = []
    setup_interceptors = lambda obj, state: []
    setup_in_graveyard = None
    setup_in_hand = None
    battlecry = None
    deathrattle = None
    spell_effect = None
    ability = None


class _PokemonCard:
    name = "Attack Text Matters"
    text = ""
    abilities = []
    setup_interceptors = None
    setup_in_graveyard = None
    setup_in_hand = None
    battlecry = None
    deathrattle = None
    spell_effect = None
    ability = {"name": "Guild Engine", "text": "Once during your turn, draw a card.", "effect_fn": lambda p, s: []}
    attacks = [
        {
            "name": "Prize Pivot",
            "damage": 40,
            "text": "If this Pokemon moved from your Bench this turn, switch it with 1 of your Benched Pokemon.",
            "effect_fn": lambda p, s: [],
        }
    ]


class _ResolveCard:
    name = "Resolve Matters"
    text = "Draw a card, then discard a card."
    abilities = []
    attacks = []
    setup_interceptors = None
    setup_in_graveyard = None
    setup_in_hand = None
    battlecry = None
    deathrattle = None
    spell_effect = None
    resolve = lambda targets, state: []
    ability = None


def test_card_depth_rewards_rules_hooks_and_clause_density():
    assert card_depth(_DeepCard())["score"] > card_depth(_TinyCard())["score"]


def test_card_depth_counts_resolve_hooks_as_wired_behavior():
    row = card_depth(_ResolveCard())
    assert row["wired_hooks"] == 1
    assert row["score"] > card_depth(_TinyCard())["score"]


def test_card_depth_includes_pokemon_attacks_and_abilities():
    row = card_depth(_PokemonCard())
    assert row["wired_hooks"] == 2
    assert "Prize Pivot" in row["text"]
    assert row["score"] >= 40


def test_summarize_set_reports_thin_cards():
    summary = summarize_set([_TinyCard(), _DeepCard()], thin_threshold=28)
    assert summary["card_count"] == 2
    assert summary["thin_count"] == 1
    assert summary["thinnest"][0]["name"] == "Tiny"


def test_build_report_includes_modern_benchmark_for_custom_sets():
    report = build_report(["mtg_pkh"], thin_threshold=28)
    assert report["schema_version"] == "hyperdraft.custom_set_depth_report.v1"
    assert "modern_mtg" in report["sets"]
    assert "mtg_pkh" in report["sets"]
    assert report["sets"]["mtg_pkh"]["benchmark_ratio"] > 0


def test_compare_reports_reports_deltas():
    before = {
        "sets": {
            "x": {
                "label": "X",
                "avg_score": 10,
                "benchmark_ratio": 0.2,
                "thin_pct": 50,
                "wired_pct": 20,
            }
        }
    }
    after = {
        "sets": {
            "x": {
                "label": "X",
                "avg_score": 16,
                "benchmark_ratio": 0.32,
                "thin_pct": 25,
                "wired_pct": 35,
            }
        }
    }
    comparison = compare_reports(before, after)
    row = comparison["sets"]["x"]
    assert row["avg_score"]["delta"] == 6
    assert row["benchmark_ratio"]["delta"] == 0.12
    assert row["thin_pct"]["delta"] == -25
    assert row["wired_pct"]["delta"] == 15
