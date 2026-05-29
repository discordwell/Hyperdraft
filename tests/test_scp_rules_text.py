"""Unit tests for the SCP player-facing rules-text generator.

``src/cards/scp/rules_text.py`` turns the structured mechanic fields on an SCP
CardDefinition into readable RULES lines for the card viewer and the in-game
board. These tests pin the phrasing contract (so a glossary edit that breaks a
keyword reminder is caught) and assert the whole card pool generates cleanly.
"""

from types import SimpleNamespace

import pytest

from src.cards.scp.rules_text import (
    SCP_ALT_WIN_GLOSSARY,
    SCP_KEYWORD_GLOSSARY,
    keyword_reminder,
    scp_rules_lines,
)


def _card(**attrs):
    """A duck-typed stand-in for a CardDefinition (scp_rules_lines uses getattr)."""
    defaults = dict(
        scp_skills={},
        scp_aura={},
        scp_bonus={},
        scp_contained_bonus={},
        scp_keywords=[],
        scp_mnestic=False,
        scp_antimeme=0,
        scp_cog_hazard=0,
        scp_alt_win=None,
    )
    defaults.update(attrs)
    return SimpleNamespace(**defaults)


# --------------------------------------------------------------------------- #
# Auras / bonuses (declarative numeric effects currently invisible in the UI)
# --------------------------------------------------------------------------- #


def test_aura_any_scope():
    lines = scp_rules_lines(_card(scp_aura={"any": {"research": 1}}))
    assert lines == ["All your personnel get +1 research while this is active."]


def test_aura_subtype_scope():
    lines = scp_rules_lines(_card(scp_aura={"subtype:Scientist": {"research": 1}}))
    assert lines == ["Your Scientist personnel get +1 research while this is active."]


def test_aura_multi_task_comma_joined_in_task_order():
    lines = scp_rules_lines(_card(scp_aura={"any": {"suppress": 1, "contain": 2}}))
    # canonical order is contain, research, suppress
    assert lines == ["All your personnel get +2 contain, +1 suppress while this is active."]


def test_site_bonus_facility():
    lines = scp_rules_lines(_card(scp_bonus={"research": 1, "contain": 1}))
    assert lines == ["While active, your checks get +1 contain, +1 research."]


def test_contained_bonus_anomaly():
    lines = scp_rules_lines(_card(scp_contained_bonus={"research": 2}))
    assert lines == ["While contained, your checks get +2 research."]


# --------------------------------------------------------------------------- #
# Skill stat-line is intentionally NOT repeated (panel / grid already show it)
# --------------------------------------------------------------------------- #


def test_bare_skill_stat_line_is_not_in_rules():
    assert scp_rules_lines(_card(scp_skills={"research": 3, "contain": 1})) == []


# --------------------------------------------------------------------------- #
# Keyword reminders (parameterized + flag-based)
# --------------------------------------------------------------------------- #


def test_parameterized_keyword_substitutes_integer():
    lines = scp_rules_lines(_card(scp_keywords=["Phylactery Audit 2"]))
    assert len(lines) == 1
    assert lines[0].startswith("Phylactery Audit 2: ")
    assert "2 ethics debt" in lines[0]


def test_cognitive_hazard_flag_has_no_plural_bug():
    lines = scp_rules_lines(_card(scp_cog_hazard=1))
    assert lines == [
        "Cognitive Hazard 1: At the start of each opponent's turn they discard 1 "
        "from hand unless they control an active Mnestic personnel."
    ]
    assert "1 cards" not in lines[0]


def test_antimeme_flag_emitted_with_threshold():
    lines = scp_rules_lines(_card(scp_antimeme=3))
    assert len(lines) == 1
    assert lines[0].startswith("Antimeme 3: ")
    assert "at 3 counters it is forgotten" in lines[0]


def test_mnestic_flag_emits_reminder():
    lines = scp_rules_lines(_card(scp_mnestic=True))
    assert len(lines) == 1
    assert lines[0].startswith("Mnestic: ")


def test_mnestic_not_duplicated_when_flag_and_keyword_both_present():
    lines = scp_rules_lines(_card(scp_mnestic=True, scp_keywords=["Mnestic"]))
    assert len([ln for ln in lines if ln.startswith("Mnestic:")]) == 1


def test_unknown_keyword_is_skipped_not_crashed():
    assert scp_rules_lines(_card(scp_keywords=["Totally Made Up Keyword"])) == []


def test_keyword_reminder_bare_vs_parameterized():
    # bare: the "{n} " placeholder is elided, leaving a natural sentence
    bare = keyword_reminder("Brief")
    assert bare is not None and "{n}" not in bare
    # parameterized: integer substituted
    assert "2 briefing" in keyword_reminder("Brief 2")


# --------------------------------------------------------------------------- #
# Alt-win rider + ordering
# --------------------------------------------------------------------------- #


def test_alt_win_rider_appended_last():
    lines = scp_rules_lines(
        _card(scp_aura={"any": {"research": 1}}, scp_alt_win="thaumiel")
    )
    assert lines[0].startswith("All your personnel")
    assert lines[-1] == SCP_ALT_WIN_GLOSSARY["thaumiel"]


def test_unknown_alt_win_is_skipped():
    assert scp_rules_lines(_card(scp_alt_win="not_a_real_alt_win")) == []


# --------------------------------------------------------------------------- #
# Whole-pool integration: every SCP card generates cleanly
# --------------------------------------------------------------------------- #


def test_full_pool_generates_list_of_strings_without_error():
    from src.cards.scp import SCP_CARDS

    assert SCP_CARDS, "SCP card pool should be non-empty"
    for name, card in SCP_CARDS.items():
        lines = scp_rules_lines(card)
        assert isinstance(lines, list), name
        assert all(isinstance(ln, str) and ln for ln in lines), name


def test_glossary_templates_are_well_formed_parameterized_and_bare():
    # Both the numbered AND the bare rendering must be clean — the bare form
    # is reachable in the real pool (Brief/Blackfile/Redact appear with no N),
    # so it must not leave a dangling token, doubled space, "some", or a
    # noun-less verb like "discards from".
    for family in SCP_KEYWORD_GLOSSARY:
        numbered = keyword_reminder(f"{family} 2")
        bare = keyword_reminder(family)
        for rendered in (numbered, bare):
            assert rendered is not None, family
            assert "{n}" not in rendered, family
            assert "  " not in rendered, f"doubled space in {family!r}: {rendered!r}"
            assert " some " not in rendered, f"'some' fallback leaked in {family!r}: {rendered!r}"
            assert "discards from" not in rendered, f"noun-less verb in {family!r}: {rendered!r}"


def test_redact_bare_is_grammatical():
    # Regression: the keyword tag "Redact" never carries an integer, so its
    # reminder must read naturally without one.
    assert keyword_reminder("Redact") == (
        "The opponent discards cards from hand (lowest red tape first)."
    )


def test_negative_aura_delta_keeps_single_sign():
    # Regression: signed formatting must not produce "+-2" for a debuff.
    lines = scp_rules_lines(_card(scp_aura={"any": {"research": -2}}))
    assert lines == ["All your personnel get -2 research while this is active."]
    assert "+-" not in lines[0]


if __name__ == "__main__":  # allow direct execution as well as pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
