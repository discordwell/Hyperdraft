"""Stage 7.5a — FBN text/code drift check.

Asserts that for every card whose printed text mentions a mechanic with a
numeric parameter (e.g. ``"Compleation Vector 2"``), the corresponding
engine attribute (``card.scp_compleation_vector``) holds the SAME number.

Because the FBN helper factories
(``_compleation``, ``_phylactery_audit``, ``_spark_containment``,
``_leyline_saturation``, ``_planar_rift``, ``_dragon_hoard``,
``_annihilation_wave``) both stamp the attribute AND append the keyword
in a single call, drift here would indicate either (a) a bespoke card
that bypassed the helper, or (b) hand-edited printed text that ran away
from the helper's numeric arg.

Run via ``python -m pytest tests/test_fbn_text_drift.py``.
"""
from __future__ import annotations

import re

import pytest

from src.cards.scp.foundations_beyond import FBN_CARDS


# Map printed-text keyword stem -> the GameObject/CardDefinition attribute
# the helper writes when given numeric arg N.
_NUMERIC_MECHANICS: dict[str, str] = {
    "Compleation Vector": "scp_compleation_vector",
    "Phylactery Audit": "scp_phylactery_audit",
    "Spark Containment": "scp_spark_containment",
    "Leyline Saturation": "scp_leyline_saturation",
    "Planar Rift": "scp_planar_rift",
    "Dragon Hoard": "scp_dragon_hoard",
    "Annihilation Wave": "scp_annihilation_wave",
}


# Cards whose text mentions a mechanic in a *non-tagger* context (e.g. as
# part of a triggered effect's body: "Planar Rift 3 trigger fires"). These
# cards intentionally don't carry the mechanic attribute — the effect_fn
# does the work. Surface them so future runs don't silently lose drift
# coverage.
_SKIPPED_CARDS: set[str] = {
    "Ambient Saturation Sweep",            # procedure: fires LS in effect_fn
    "Rift Stabilization Protocol",         # procedure: fires Planar Rift in effect_fn
    "Class-IV Rift Audit",                 # procedure: fires Planar Rift in effect_fn
    "Multiversal Containment Sweep",       # procedure: cascade rift trigger
    "Mnestic Necromancy Audit",            # procedure: phylactery audit as flavor
    "Phantom Recall Audit",                # procedure: phylactery audit as flavor
    "Ambient Specter Detention Site",      # facility: triggers LS in effect_fn
}


def _extract_numeric_keywords(text: str) -> list[tuple[str, int]]:
    """Return ``[(mechanic_name, n), ...]`` for every numeric-mechanic
    reference in ``text``. Skips structural mentions like "Compleation
    Vector triggers" with no number.
    """
    if not text:
        return []
    out: list[tuple[str, int]] = []
    for stem in _NUMERIC_MECHANICS:
        for match in re.finditer(rf"\b{re.escape(stem)} (\d+)\b", text):
            out.append((stem, int(match.group(1))))
    return out


def test_fbn_text_code_drift():
    """For every FBN card, the printed mechanic-N values must match the
    engine attribute the helper stamped.
    """
    drifts: list[str] = []
    for name, card in FBN_CARDS.items():
        if name in _SKIPPED_CARDS:
            continue
        printed = getattr(card, "text", None) or ""
        # Bucket mentions by mechanic. A card may mention the same mechanic
        # multiple times with different Ns — e.g. "Leyline Saturation 2.
        # Grant Leyline Saturation 1 to others." Drift fires only when the
        # CARD'S OWN N (stamped by the helper) doesn't appear ANYWHERE in
        # the text, or when the helper wasn't applied at all despite the
        # text claiming the mechanic.
        mentions: dict[str, list[int]] = {}
        for stem, printed_n in _extract_numeric_keywords(printed):
            mentions.setdefault(stem, []).append(printed_n)
        for stem, printed_ns in mentions.items():
            attr = _NUMERIC_MECHANICS[stem]
            code_n = getattr(card, attr, None)
            if code_n is None:
                drifts.append(
                    f"{name}: text mentions {stem} {printed_ns} but "
                    f"{attr} is unset (helper not applied?)"
                )
            elif code_n not in printed_ns:
                drifts.append(
                    f"{name}: text mentions {stem} {printed_ns} but "
                    f"{attr}={code_n} (drift)"
                )
    if drifts:
        pytest.fail(
            f"{len(drifts)} text/code drift failures:\n  "
            + "\n  ".join(drifts[:25])
        )


def test_fbn_text_drift_keyword_stamps_present():
    """Every numeric-mechanic attribute on a card must also show up in
    ``scp_keywords`` so analytics + frontend don't miss the badge.
    """
    missing: list[str] = []
    for name, card in FBN_CARDS.items():
        for stem, attr in _NUMERIC_MECHANICS.items():
            n = getattr(card, attr, None)
            if n is None:
                continue
            stamp = f"{stem} {n}"
            keywords = getattr(card, "scp_keywords", None) or []
            if stamp not in keywords:
                missing.append(f"{name}: has {attr}={n} but no {stamp!r} in scp_keywords")
    if missing:
        pytest.fail(
            f"{len(missing)} cards missing keyword stamps:\n  "
            + "\n  ".join(missing[:25])
        )
