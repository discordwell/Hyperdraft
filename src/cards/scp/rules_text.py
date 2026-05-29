"""Player-facing rules text for SCP cards.

The SCP card pool keeps its mechanics in *structured* fields on the
``CardDefinition`` (``scp_skills``, ``scp_aura``, ``scp_bonus``,
``scp_contained_bonus``, the ``scp_mnestic`` / ``scp_antimeme`` /
``scp_cog_hazard`` flags, the ``scp_keywords`` list and ``scp_alt_win``).
The single ``text`` field is sometimes a mechanical restatement (core +
Site-Zero cards) and sometimes pure SCP-wiki flavor (Mnestic Reset,
Foundations Beyond), so reading a card never tells you reliably what it
*does* — and the auras (153 cards!) and contained bonuses are not surfaced
in the UI at all.

``scp_rules_lines`` turns those structured fields into a small list of
plain rules sentences, so both the card viewer and the in-game board can
render a canonical RULES block separate from the flavor ``text``. It is a
pure function of the ``CardDefinition`` and reads attributes duck-typed, so
it imports nothing from the engine (no circular-import / load-order risk).

The keyword glossary is family-level: a keyword like ``"Blackfile 2"`` names
the *family* (Blackfile = paperwork sabotage) while the card's own ``text``
carries the exact parameters. Every entry below was verified against the
consuming engine code (``src/engine/scp.py``) — see the comment on each.
"""

from __future__ import annotations

import re
from typing import Any, Optional


# Canonical task order, matching ``scp.TASKS`` in the engine.
_TASKS = ("contain", "research", "suppress")


# ---------------------------------------------------------------------------
# Keyword glossary. Keys are the family name (the trailing integer, if any,
# is stripped before lookup). ``{n}`` is replaced with the keyword's integer
# when present, or elided when the keyword is bare. Reminders are deliberately
# one sentence and describe the *general* effect; per-card specifics live in
# the card's flavor ``text``.
# ---------------------------------------------------------------------------
SCP_KEYWORD_GLOSSARY: dict[str, str] = {
    # --- Site-Zero (SZB) procedure / anomaly families ---
    # site_zero_broken_masquerade.py: _brief hooks add to site["briefing"].
    "Brief": "Add {n} briefing to your site.",
    # _resolve_blackfile: misfile_dossier(N) on a rival pending dossier, force_audit if none.
    "Blackfile": "Add {n} paperwork to a rival's pending dossier; if they have none, force an audit instead.",
    # _overexpose_procedure: secrecy -2, archive +1, clearance +1.
    "Overexpose": "Spend 2 secrecy to gain +1 archive and +1 clearance.",
    # _quarantine_procedure: apply a protocol + mood to a target active anomaly.
    "Quarantine": "Apply a containment protocol and mood to a target active anomaly, shifting its check difficulty.",
    # cross_contain / _anchor: bind a contained anomaly to an active one.
    "Anchor": "Bind one of your contained anomalies to an active one, dampening the active anomaly's breach.",
    "Cross-Containment": "Bind a contained anomaly to an active one to reduce breach and gain an archive.",
    # _rotation_procedure: refund a used assignment slot + refresh one exhausted staff.
    "Rotation": "Refund a used assignment slot and refresh an exhausted staff member.",
    # --- Foundations Beyond (FBN) families (engine apply_* hooks) ---
    # apply_phylactery_audit: on memory-hole, return to hand for X ethics if debt+X<=8.
    "Phylactery Audit": "When this would be forgotten, if it won't push your ethics debt past 8 it returns to your hand for {n} ethics debt; otherwise it stays exiled.",
    # apply_leyline_saturation: opp opens a non-anomaly dossier -> your active anomalies lose N suppression.
    "Leyline Saturation": "When an opponent opens a procedure, facility, or mandate, each of your active anomalies loses {n} suppression (gaining hazard) until your end of turn.",
    # apply_spark_containment: each contain success adds N clearance; first cross of 6/turn ticks a dossier.
    "Spark Containment": "Each successful containment adds {n} clearance; the first time your clearance crosses 6 each turn, tick down one of your pending dossiers.",
    # apply_compleation_vector: end of opp turn, N counters on their best non-Mnestic personnel; steal at 3.
    "Compleation Vector": "At the end of each opponent's turn, place {n} counters on their strongest non-Mnestic personnel; at 3 counters you take control of it.",
    # apply_annihilation_wave: on breach tick, redact N opposing dossiers and +N breach to each opponent.
    "Annihilation Wave": "On each breach tick, redact {n} of the opponent's dossiers and raise every opponent's breach by {n}.",
    # _active_bonus dragon walk: archived Dragons add X to every task check, capped +6.
    "Dragon Hoard": "While archived, each Dragon you have filed adds {n} to all of your task checks (capped at +6 total).",
    # _site_defaults rift_window + _planar_rift: on contain, exile top X to a window you may play from this turn.
    "Planar Rift": "When contained, exile the top {n} cards of your library to a rift window you may play from this turn, bypassing the paperwork queue.",
    # apply_wurm_devourer: successful research test -> +2 suppression instead of archive; alt-win counter.
    "Wurm Devourer": "When a research test against it succeeds, it is suppressed (+2) instead of archived and counts toward the Wurm Apex victory.",
    # redact_opposing: opponent discards N cards (lowest red tape first). The
    # keyword tag never carries the count (it lives in the card's effect), so
    # this reminder stays number-free.
    "Redact": "The opponent discards cards from hand (lowest red tape first).",
    # goi_raid: external pressure — agitate worst anomaly / jam a dossier / cost secrecy.
    "GOI": "Group-of-Interest raid: pressures the target — agitating their worst anomaly, jamming a dossier, or costing them secrecy.",
    # --- Flag-based keywords (Mnestic / Antimeme / Cognitive Hazard) ---
    # has_mnestic + tick_antimeme_counters + apply_cognitive_hazard_start + apply_compleation_vector.
    "Mnestic": "While active, blocks antimemetic decay on your anomalies and shields you from Cognitive Hazard and Compleation Vector.",
    # tick_antimeme_counters: +1 forget counter each end step (no unexhausted Mnestic); forgotten at N.
    "Antimeme": "At each of your end steps (with no unexhausted Mnestic personnel) it gains a forget counter; at {n} counters it is forgotten (exiled).",
    # apply_cognitive_hazard_start: opp discards X at start of their turn unless they have active Mnestic.
    "Cognitive Hazard": "At the start of each opponent's turn they discard {n} from hand unless they control an active Mnestic personnel.",
    # personnel.py: cheap fragile body, drains first under Cognitive Hazard, may carry Mnestic Wake.
    "Bystander": "Cheap, fragile personnel: drains first under Cognitive Hazard and may carry Mnestic Wake.",
}


# ``scp_alt_win`` values -> the alternate-victory condition. Verified against
# check_scp_victory in src/engine/scp.py.
SCP_ALT_WIN_GLOSSARY: dict[str, str] = {
    "redaction": "Alternate victory (Redaction): meet the redaction-press lock condition.",
    "thaumiel": "Alternate victory (Thaumiel): control 3+ contained anomalies with 0 breach.",
    "veil_lockdown": "Alternate victory (Veil Lockdown): reach 3+ archives with 0 breach.",
    "ethics_audit": "Alternate victory (Ethics Audit): reach 4+ archives with 7+ secrecy.",
    "public_panic": "Alternate victory (Public Panic): reach 4+ archives while an opponent is at 6 or less secrecy.",
    "memory_hole": "Alternate victory (Memory Hole): 3+ anomalies forgotten (any player) with 8+ secrecy.",
    "mnestic_saturation": "Alternate victory (Mnestic Saturation): 4+ active Mnestic personnel and 4+ archives.",
    "compleation_overrun": "Alternate victory (Compleation Overrun): steal 3 personnel via Compleation Vector.",
    "phylactery_chain": "Alternate victory (Phylactery Chain): return 4 cards to hand via Phylactery Audit.",
    "wurm_apex_tamed": "Alternate victory (Wurm Apex): tame 3 anomalies via Wurm Devourer.",
}


_TRAILING_INT = re.compile(r"\s+(\d+)$")


def _split_keyword(keyword: str) -> tuple[str, Optional[int]]:
    """Split ``"Phylactery Audit 2"`` -> ``("Phylactery Audit", 2)``.

    A keyword with no trailing integer (e.g. ``"Overexpose"``) returns
    ``(name, None)``.
    """
    match = _TRAILING_INT.search(keyword)
    if match:
        return keyword[: match.start()], int(match.group(1))
    return keyword, None


def _format_reminder(template: str, n: Optional[int]) -> str:
    """Substitute ``{n}`` in a glossary template.

    When the keyword is bare (``n is None``) every ``{n}`` placeholder is
    elided and any doubled whitespace collapsed, so the sentence still reads
    naturally (e.g. "Add briefing to your site.") rather than leaving a
    dangling token.
    """
    if n is None:
        out = template.replace("{n} ", "").replace(" {n}", "").replace("{n}", "")
        return " ".join(out.split())
    return template.replace("{n}", str(n))


def keyword_reminder(keyword: str) -> Optional[str]:
    """Return the one-line reminder for a keyword string, or ``None``.

    Looks up the family (trailing integer stripped) in
    ``SCP_KEYWORD_GLOSSARY`` and substitutes the integer back in.
    """
    name, n = _split_keyword(keyword)
    template = SCP_KEYWORD_GLOSSARY.get(name)
    if template is None:
        return None
    return _format_reminder(template, n)


def _fmt_task_amounts(amounts: dict[str, Any], *, signed: bool) -> str:
    """Format ``{"research": 1, "contain": 1}`` in canonical task order.

    ``signed`` prefixes a ``+`` (used for bonuses/auras). Tasks not in
    ``_TASKS`` (defensive) are appended after the known ones.
    """
    def _part(value: int, task: str) -> str:
        # ``{value:+d}`` keeps a single sign even for negatives (-2 -> "-2",
        # not "+-2"); unsigned amounts (skill stat-lines) print bare.
        return f"{value:+d} {task}" if signed else f"{value} {task}"

    parts: list[str] = []
    seen: set[str] = set()
    for task in _TASKS:
        value = int(amounts.get(task, 0) or 0)
        if value:
            parts.append(_part(value, task))
            seen.add(task)
    for task, raw in amounts.items():
        if task in seen:
            continue
        value = int(raw or 0)
        if value:
            parts.append(_part(value, task))
    return ", ".join(parts)


def _aura_scope(selector: str) -> Optional[str]:
    """Phrase an aura selector. ``None`` for selectors we don't surface."""
    if selector == "any":
        return "All your personnel"
    if isinstance(selector, str) and selector.startswith("subtype:"):
        subtype = selector.split(":", 1)[1]
        return f"Your {subtype} personnel"
    return None


def scp_rules_lines(card_def: Any) -> list[str]:
    """Build the player-facing RULES block for an SCP ``CardDefinition``.

    Returns an ordered list of plain rules sentences. Empty when the card
    has no surfaceable structured mechanics (its flavor ``text`` then stands
    alone). Pure / side-effect free.
    """
    if card_def is None:
        return []
    lines: list[str] = []

    # NOTE: the bare skill stat-line ({contain/research/suppress: N}) is
    # intentionally NOT repeated here — the card viewer renders it in a
    # "Personnel Skills" panel and the board in a C/R/S grid. This block
    # surfaces only the mechanics those stat displays DON'T show.

    # 1. Aura ("lord") effects — currently invisible in the UI.
    aura = getattr(card_def, "scp_aura", None) or {}
    for selector, deltas in aura.items():
        scope = _aura_scope(selector)
        if not scope or not deltas:
            continue
        amounts = _fmt_task_amounts(deltas, signed=True)
        if amounts:
            lines.append(f"{scope} get {amounts} while this is active.")

    # 2. Static site bonus (facility / mandate).
    bonus = getattr(card_def, "scp_bonus", None) or {}
    bonus_amounts = _fmt_task_amounts(bonus, signed=True)
    if bonus_amounts:
        lines.append(f"While active, your checks get {bonus_amounts}.")

    # 3. Contained-anomaly bonus.
    contained = getattr(card_def, "scp_contained_bonus", None) or {}
    contained_amounts = _fmt_task_amounts(contained, signed=True)
    if contained_amounts:
        lines.append(f"While contained, your checks get {contained_amounts}.")

    # 4. Keyword reminders. Gather the printed keyword list plus the three
    #    flag-based keywords, dedup by family so "Mnestic" isn't doubled.
    keywords: list[str] = list(getattr(card_def, "scp_keywords", None) or [])
    if getattr(card_def, "scp_mnestic", False) and not any(
        _split_keyword(k)[0] == "Mnestic" for k in keywords
    ):
        keywords.append("Mnestic")
    antimeme = int(getattr(card_def, "scp_antimeme", 0) or 0)
    if antimeme:
        keywords.append(f"Antimeme {antimeme}")
    cog_hazard = int(getattr(card_def, "scp_cog_hazard", 0) or 0)
    if cog_hazard:
        keywords.append(f"Cognitive Hazard {cog_hazard}")

    seen_families: set[str] = set()
    for keyword in keywords:
        family = _split_keyword(keyword)[0]
        if family in seen_families:
            continue
        reminder = keyword_reminder(keyword)
        if reminder is None:
            continue
        seen_families.add(family)
        lines.append(f"{keyword}: {reminder}")

    # 5. Alternate-victory rider.
    alt_win = getattr(card_def, "scp_alt_win", None)
    if alt_win:
        alt = SCP_ALT_WIN_GLOSSARY.get(alt_win)
        if alt:
            lines.append(alt)

    return lines


__all__ = [
    "SCP_KEYWORD_GLOSSARY",
    "SCP_ALT_WIN_GLOSSARY",
    "keyword_reminder",
    "scp_rules_lines",
]
