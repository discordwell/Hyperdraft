"""Foundations Beyond (FBN) card-side helper factories.

FBN's mechanic stack: ten verbs total — two reused (Brief N, Mnestic) and
eight new. Each helper tags a CardDefinition with a metadata attribute the
engine reads, then appends a human-readable label to ``scp_keywords`` so
analytics, frontend tooltips, and AI heuristics can introspect the card's
mechanic surface.

Card-design agents: ALWAYS run cards through ``_with_fbn_metadata`` (or the
``_fbn_card`` factory, which calls it for you) before appending to a
sub-module list. The expansion code is what wires cards into the FBN set
filter (``scp_expansion_code == "FBN"``).

The mechanic-tagger helpers (``_compleation``, ``_phylactery_audit``, etc.)
are intentionally *composable* — they take a CardDefinition, mutate it
in-place, and return it. So::

    card = _phylactery_audit(_compleation(some_card, 2), 1)

results in a card with both ``scp_compleation_vector = 2`` and
``scp_phylactery_audit = 1``, plus ``"Compleation Vector 2"`` and
``"Phylactery Audit 1"`` in ``scp_keywords``.
"""

from __future__ import annotations

from typing import Optional

from src.engine import scp
from src.engine.types import (
    CardDefinition,
    CardType,
)


EXPANSION = "Foundations Beyond"
EXPANSION_CODE = "FBN"


# ---------------------------------------------------------------------------
# Metadata + base wrappers
# ---------------------------------------------------------------------------


def _with_fbn_metadata(
    card: CardDefinition,
    *,
    archetype: str = "foundations_beyond",
    keywords: Optional[set[str]] = None,
    art_prompt: Optional[str] = None,
) -> CardDefinition:
    """Stamp the standard FBN metadata fields onto ``card``.

    ``archetype`` lets card agents split the set into the ten sub-themes
    (e.g. "phyrexian_strain", "lich_phylactery", "multiverse_rift"); the
    default "foundations_beyond" is a fallback that should never ship.

    Existing ``scp_keywords`` on the card are preserved — the mechanic
    tagger helpers append to this list, so calling ``_with_fbn_metadata``
    after a tagger does NOT clobber the keyword list.
    """
    card.scp_expansion = EXPANSION
    card.scp_expansion_code = EXPANSION_CODE
    card.scp_archetype = archetype
    existing = list(getattr(card, "scp_keywords", []) or [])
    add = sorted(set(keywords or set()))
    merged = sorted(set(existing) | set(add))
    card.scp_keywords = merged
    card.scp_art_prompt = art_prompt or (
        f"Original SCP-inspired trading card art for {card.name} from {EXPANSION}: "
        f"a captured MTG entity inside a Foundation containment cell — sterile "
        f"concrete architecture under sodium-arc light, redacted/stamped "
        f"paperwork overlays, cosmic-horror tone, clear focal subject, no text, "
        f"no logos, no card frames, high-detail digital painting."
    )
    return card


def _fbn_card(
    name: str,
    card_type: CardType,
    *,
    archetype: str = "foundations_beyond",
    keywords: Optional[set[str]] = None,
    art_prompt: Optional[str] = None,
    **make_kwargs,
) -> CardDefinition:
    """Thin wrapper around ``scp.make_scp_card`` that stamps FBN metadata.

    Use this as the default constructor for FBN cards in
    ``anomalies.py`` / ``personnel.py`` / etc. Pass any of ``make_scp_card``'s
    keyword args through ``**make_kwargs``.
    """
    card = scp.make_scp_card(name, card_type, **make_kwargs)
    return _with_fbn_metadata(card, archetype=archetype, keywords=keywords, art_prompt=art_prompt)


# ---------------------------------------------------------------------------
# Keyword append helper (used by every tagger below)
# ---------------------------------------------------------------------------


def _append_keyword(card: CardDefinition, keyword: str) -> None:
    """Append ``keyword`` to ``card.scp_keywords``, deduped + sorted."""
    existing = set(getattr(card, "scp_keywords", []) or set())
    existing.add(keyword)
    card.scp_keywords = sorted(existing)


# ---------------------------------------------------------------------------
# Mechanic taggers — each takes a CardDefinition, mutates it, returns it.
# Composable: each tagger reads/writes its own ``scp_<verb>`` attribute and
# only ever appends to ``scp_keywords``. So multiple taggers on one card
# all coexist without stepping on each other.
# ---------------------------------------------------------------------------


def _compleation(card: CardDefinition, n: int) -> CardDefinition:
    """Tag an anomaly with ``scp_compleation_vector = N``.

    The engine's ``apply_compleation_vector`` (called at end of each
    opposing turn) places N counters on the highest-skill non-Mnestic
    opposing personnel; at >=3 counters the personnel's controller flips.
    """
    if n < 1:
        raise ValueError(f"_compleation: N must be >=1, got {n!r}")
    card.scp_compleation_vector = int(n)
    _append_keyword(card, f"Compleation Vector {n}")
    return card


def _phylactery_audit(card: CardDefinition, x: int) -> CardDefinition:
    """Tag a card with ``scp_phylactery_audit = X``.

    When the card is memory-holed, the engine fires
    ``SCP_PHYLACTERY_AUDIT_OFFER`` and auto-accepts when
    ``ethics_debt + X <= 8``; on accept the card is returned to hand and
    the controller's ``phylactery_audits`` counter bumps (alt-win at 4+).
    """
    if x < 1:
        raise ValueError(f"_phylactery_audit: X must be >=1, got {x!r}")
    card.scp_phylactery_audit = int(x)
    _append_keyword(card, f"Phylactery Audit {x}")
    return card


def _spark_containment(card: CardDefinition, n: int) -> CardDefinition:
    """Tag a personnel/facility/mandate with ``scp_spark_containment = N``.

    On every successful ``SCP_CONTAINED`` event for the controller, the
    engine bumps clearance by N; the first time clearance crosses 6 each
    turn it fires an extra ``SCP_PAPERWORK_TICK``.
    """
    if n < 1:
        raise ValueError(f"_spark_containment: N must be >=1, got {n!r}")
    card.scp_spark_containment = int(n)
    _append_keyword(card, f"Spark Containment {n}")
    return card


def _leyline_saturation(card: CardDefinition, n: int) -> CardDefinition:
    """Tag an anomaly with ``scp_leyline_saturation = N``.

    When an opposing player opens a Procedure/Facility/Mandate, every
    active anomaly the saturating player controls drops
    ``scp_suppressed`` by N (negative suppression = bonus hazard at
    breach-tick time). Cleared at the saturator's end of turn.
    """
    if n < 1:
        raise ValueError(f"_leyline_saturation: N must be >=1, got {n!r}")
    card.scp_leyline_saturation = int(n)
    _append_keyword(card, f"Leyline Saturation {n}")
    return card


def _planar_rift(card: CardDefinition, x: int) -> CardDefinition:
    """Tag an anomaly with ``scp_planar_rift = X``.

    On ``SCP_CONTAINED``, the engine exiles top X of the controller's
    library into a transient ``rift_window``; cards there may be played
    via ``play_from_rift_window`` (skips the paperwork queue, no red
    tape). Cards still in the window at end-of-turn return to the top
    of the library.
    """
    if x < 1:
        raise ValueError(f"_planar_rift: X must be >=1, got {x!r}")
    card.scp_planar_rift = int(x)
    _append_keyword(card, f"Planar Rift {x}")
    return card


def _dragon_hoard(card: CardDefinition, x: int) -> CardDefinition:
    """Tag a Dragon-subtype card with ``scp_dragon_hoard = X``.

    Pure state-time read in ``_active_bonus``: each archived card with
    subtype "Dragon" and ``scp_dragon_hoard = X`` adds X to all of the
    archiver's tests, capped at +6 per test (engine guardrail).

    Caller responsibility: ensure ``card.characteristics.subtypes`` already
    contains ``"Dragon"`` — the engine does not auto-tag the subtype.
    """
    if x < 1:
        raise ValueError(f"_dragon_hoard: X must be >=1, got {x!r}")
    card.scp_dragon_hoard = int(x)
    _append_keyword(card, f"Dragon Hoard {x}")
    return card


def _annihilation_wave(card: CardDefinition, n: int) -> CardDefinition:
    """Tag an anomaly with ``scp_annihilation_wave = N``.

    On every ``SCP_BREACH_TICK`` for the anomaly's controller, the engine
    redacts N opposing dossiers (discard + event tag) AND bumps every
    opposing player's breach by N. Composes Redact + breach-pump into one
    keyword so codegen agents don't have to re-stitch two effects per
    Eldrazi-flavored anomaly.
    """
    if n < 1:
        raise ValueError(f"_annihilation_wave: N must be >=1, got {n!r}")
    card.scp_annihilation_wave = int(n)
    _append_keyword(card, f"Annihilation Wave {n}")
    return card


def _wurm_devourer(card: CardDefinition) -> CardDefinition:
    """Tag a Wurm anomaly with ``scp_wurm_devourer = True``.

    When a research test against this anomaly succeeds, the engine swaps
    the normal curiosity-tick / archives gain for ``scp_suppressed += 2``
    (less hazard) and bumps the controller's ``wurms_tamed`` counter
    (alt-win ``wurm_apex_tamed`` at 3+).
    """
    card.scp_wurm_devourer = True
    _append_keyword(card, "Wurm Devourer")
    return card


def _brief(card: CardDefinition, n: int) -> CardDefinition:
    """Tag a card with the Brief N keyword (reused from SZB).

    Brief tokens are already tracked under ``site["briefing"]`` by the
    SZB-era engine code; this helper only stamps the keyword label so
    analytics and frontend see "Brief N" on the card.

    Card-side effect agents should still emit briefing increments via
    the existing on-reveal / effect callable that bumps ``site["briefing"]``
    by N — there is no FBN engine hook for Brief; only the label.
    """
    if n < 1:
        raise ValueError(f"_brief: N must be >=1, got {n!r}")
    card.scp_brief = int(n)
    _append_keyword(card, f"Brief {n}")
    return card


def _mnestic_personnel(card: CardDefinition) -> CardDefinition:
    """Tag a personnel as Mnestic (reused from MNR).

    Pure mirror of MNR's ``_mnestic_personnel`` — the engine's
    ``has_mnestic`` query checks ``card.scp_mnestic = True`` (printed) or
    ``state.scp_mnestic_gained`` (mid-game). FBN uses this for Phyrexian
    Strain (Mnestic researchers resist compleation's cognitive-rewrite
    component) and Lich Phylactery (Mnestic personnel see past Phylactery
    Audit's memory-hole misdirection).

    Caller responsibility: add ``"Mnestic"`` to subtypes if you want
    selector targeting (``aura: {"subtype:Mnestic": ...}``).
    """
    card.scp_mnestic = True
    _append_keyword(card, "Mnestic")
    return card


__all__ = [
    "EXPANSION",
    "EXPANSION_CODE",
    "_with_fbn_metadata",
    "_fbn_card",
    "_compleation",
    "_phylactery_audit",
    "_spark_containment",
    "_leyline_saturation",
    "_planar_rift",
    "_dragon_hoard",
    "_annihilation_wave",
    "_wurm_devourer",
    "_brief",
    "_mnestic_personnel",
]
