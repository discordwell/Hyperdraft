"""Tests for art_harness's --cards-json loader path and PIP//30 style config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.new_set.art_harness import (
    _find_items_list,
    build_prompt,
    load_cards_json,
    load_style,
)


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_find_items_picks_first_list_of_dicts(tmp_path):
    data = {
        "deckIds": ["a", "b", "c"],
        "cards": [{"id": "x", "name": "X"}, {"id": "y", "name": "Y"}],
    }
    items = _find_items_list(data, items_key=None)
    assert [it["id"] for it in items] == ["x", "y"]


def test_find_items_respects_explicit_key(tmp_path):
    data = {
        "primary": [{"id": "p"}],
        "secondary": [{"id": "s"}],
    }
    items = _find_items_list(data, items_key="secondary")
    assert [it["id"] for it in items] == ["s"]


def test_find_items_rejects_when_ambiguous_without_key():
    with pytest.raises(ValueError):
        _find_items_list({"a": 1, "b": 2}, items_key=None)


def test_find_items_rejects_when_multiple_list_of_dicts_candidates():
    """A JSON file with two top-level list-of-dicts arrays must require an
    explicit items_key — picking the first would be a silent mis-load."""
    data = {
        "metadata": [{"version": 1}],
        "cards": [{"id": "x"}],
    }
    with pytest.raises(ValueError, match="multiple list-of-dicts"):
        _find_items_list(data, items_key=None)
    items = _find_items_list(data, items_key="cards")
    assert [it["id"] for it in items] == ["x"]


def test_load_cards_json_basic(tmp_path):
    src = _write_json(tmp_path / "cards.json", {
        "cards": [
            {"id": "fireball", "name": "Fireball", "text": "Deal 6 damage."},
            {"id": "heal", "name": "Heal", "text": "Restore 5 health."},
        ],
    })
    cards = load_cards_json([src])
    assert set(cards) == {"Fireball", "Heal"}
    assert cards["Fireball"].text == "Deal 6 damage."
    assert cards["Fireball"].id == "fireball"


def test_load_cards_json_pip30_shape_with_lookup(tmp_path):
    """The real PIP//30 case: nameKey/descriptionKey + en.json translation."""
    cards_path = _write_json(tmp_path / "starter.json", {
        "cards": [
            {
                "id": "read_stack_trace",
                "nameKey": "card.read_stack_trace.name",
                "descriptionKey": "card.read_stack_trace.description",
                "family": "Code",
                "cost": 1,
                "damage": 5,
            },
            {
                "id": "deep_breath",
                "nameKey": "card.deep_breath.name",
                "descriptionKey": "card.deep_breath.description",
                "family": "Survival",
                "cost": 1,
            },
        ],
    })
    lookup_path = tmp_path / "en.json"
    lookup_path.write_text(json.dumps({
        "card.read_stack_trace.name": "Read Stack Trace",
        "card.read_stack_trace.description": "Deal 5. Add 8s to the next focus window.",
        "card.deep_breath.name": "Deep Breath",
        "card.deep_breath.description": "Heal 3 Stress. Gain 6 block.",
    }), encoding="utf-8")

    cards = load_cards_json(
        [cards_path],
        name_key="nameKey",
        text_key="descriptionKey",
        text_lookup_path=lookup_path,
    )
    assert set(cards) == {"Read Stack Trace", "Deep Breath"}
    assert cards["Read Stack Trace"].text.startswith("Deal 5")
    assert cards["Read Stack Trace"].family == "Code"
    assert cards["Deep Breath"].family == "Survival"


def test_load_cards_json_skips_entries_with_missing_name(tmp_path):
    src = _write_json(tmp_path / "partial.json", {
        "cards": [
            {"id": "good", "name": "Good"},
            {"id": "nameless"},
            {"id": "blank", "name": ""},
        ],
    })
    cards = load_cards_json([src])
    assert list(cards) == ["Good"]


def test_load_cards_json_merges_multiple_files(tmp_path):
    a = _write_json(tmp_path / "a.json", {"cards": [{"name": "Alpha"}]})
    b = _write_json(tmp_path / "b.json", {"cards": [{"name": "Beta"}]})
    cards = load_cards_json([a, b])
    assert set(cards) == {"Alpha", "Beta"}


def test_load_cards_json_unresolved_lookup_falls_back_to_raw_key(tmp_path):
    """If a translation is missing from the lookup, we keep the raw key —
    better to surface a weird-looking name than to silently drop the entry."""
    src = _write_json(tmp_path / "c.json", {
        "cards": [{"nameKey": "card.missing.name", "descriptionKey": "card.missing.desc"}],
    })
    lookup = tmp_path / "en.json"
    lookup.write_text(json.dumps({}), encoding="utf-8")
    cards = load_cards_json(
        [src], name_key="nameKey", text_key="descriptionKey", text_lookup_path=lookup,
    )
    assert "card.missing.name" in cards


def test_pip30_style_categorizes_card_family():
    style = load_style("src.cards.pip30.style")
    code_card = type("C", (), {"family": "Code"})()
    process_card = type("C", (), {"family": "Process"})()
    survival_card = type("C", (), {"family": "Survival"})()
    shadow_card = type("C", (), {"family": "Shadow"})()
    assert style.categorize(code_card) == "code"
    assert style.categorize(process_card) == "process"
    assert style.categorize(survival_card) == "survival"
    assert style.categorize(shadow_card) == "shadow"


def test_pip30_style_categorizes_enemy_and_challenge():
    style = load_style("src.cards.pip30.style")
    enemy = type("E", (), {"intentKey": "enemy.flaky_test.intent", "maxResolve": 20})()
    challenge = type("Ch", (), {"codeText": "public void Foo() {}"})()
    fallback = type("X", (), {})()
    assert style.categorize(enemy) == "enemy"
    assert style.categorize(challenge) == "challenge"
    assert style.categorize(fallback) == "object"


def test_load_cards_json_multi_name_key_covers_cards_and_challenges(tmp_path):
    """Real PIP30 case: cards use nameKey, challenges use titleKey. One
    --cards-json-name-key 'nameKey,titleKey' invocation should load both."""
    cards_path = _write_json(tmp_path / "cards.json", {
        "cards": [{"nameKey": "card.x.name", "descriptionKey": "card.x.desc", "family": "Code"}],
    })
    challenges_path = _write_json(tmp_path / "challenges.json", {
        "challenges": [{
            "titleKey": "challenge.y.title",
            "promptKey": "challenge.y.prompt",
            "codeText": "var x = 1;",
        }],
    })
    lookup = tmp_path / "en.json"
    lookup.write_text(json.dumps({
        "card.x.name": "Card X",
        "card.x.desc": "Does a thing.",
        "challenge.y.title": "Challenge Y",
        "challenge.y.prompt": "Find the bug.",
    }), encoding="utf-8")

    cards = load_cards_json(
        [cards_path, challenges_path],
        name_key="nameKey,titleKey",
        text_key="descriptionKey,promptKey",
        text_lookup_path=lookup,
    )
    assert set(cards) == {"Card X", "Challenge Y"}
    style = load_style("src.cards.pip30.style")
    assert style.categorize(cards["Card X"]) == "code"
    assert style.categorize(cards["Challenge Y"]) == "challenge"


def test_load_cards_json_first_string_picks_first_non_empty(tmp_path):
    """If the first candidate name-key is empty, fall through to the next."""
    src = _write_json(tmp_path / "mix.json", {
        "cards": [
            {"nameKey": "", "titleKey": "fallback.title"},
            {"nameKey": "primary.name", "titleKey": "ignored.title"},
        ],
    })
    lookup = tmp_path / "en.json"
    lookup.write_text(json.dumps({
        "primary.name": "Primary",
        "fallback.title": "Fallback",
    }), encoding="utf-8")
    cards = load_cards_json(
        [src],
        name_key="nameKey,titleKey",
        text_lookup_path=lookup,
    )
    assert set(cards) == {"Primary", "Fallback"}


def test_pip30_build_prompt_contains_headline_and_category(tmp_path):
    """End-to-end: JSON entry → prompt string mentions headline + category flavor."""
    cards_path = _write_json(tmp_path / "starter.json", {
        "cards": [{
            "id": "read_stack_trace",
            "nameKey": "card.read_stack_trace.name",
            "descriptionKey": "card.read_stack_trace.description",
            "family": "Code",
        }],
    })
    lookup_path = tmp_path / "en.json"
    lookup_path.write_text(json.dumps({
        "card.read_stack_trace.name": "Read Stack Trace",
        "card.read_stack_trace.description": "Deal 5.",
    }), encoding="utf-8")

    cards = load_cards_json(
        [cards_path],
        name_key="nameKey",
        text_key="descriptionKey",
        text_lookup_path=lookup_path,
    )
    style = load_style("src.cards.pip30.style")
    prompt = build_prompt(cards["Read Stack Trace"], style)
    assert "Read Stack Trace" in prompt
    assert "gouache" in prompt
    assert "backlit mechanical keyboard" in prompt
    assert "Deal 5" in prompt
