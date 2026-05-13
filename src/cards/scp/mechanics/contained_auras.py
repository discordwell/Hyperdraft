"""Contained-state auras: anomalies that earn their keep while locked away.

Each entry sets ``card.scp_contained_bonus = {task: int, ...}`` on the shared
``CardDefinition`` instance. The engine's ``_active_bonus`` reads this dict
from anomalies in ``state.scp_contained`` and folds the value into the
relevant task total (research / contain / suppress) — same shape as
``scp_bonus`` on facilities, just gated on the "contained" zone bucket.

This is the Thaumiel payoff lever: keeping an anomaly contained instead of
shoveling it into the graveyard now gives a steady, board-visible bonus.

Boundary (W2):
- We only set ``scp_contained_bonus`` and append a line to ``card.text``.
- We never touch ``scp_on_reveal``, ``scp_on_test``, ``scp_on_test_fail``,
  or ``scp_aura`` — those belong to sibling worktrees.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.types import CardDefinition


# Map of anomaly name -> {task: int} contained-state bonus.
# Tasks are exactly the SCP engine's task names: "research", "contain",
# "suppress". Multi-task dicts stack on every relevant assignment.
CONTAINED_BONUSES: dict[str, dict[str, int]] = {
    # ---- CORE anomalies ----
    "Oracle Mold": {"research": 1},
    "Borrowed Moon": {"research": 1},
    "Unlicensed Heaven": {"research": 2, "contain": 1},
    "Antimemetic Orchard": {"research": 1, "suppress": 1},
    "Hostile Nursery Rhyme": {"research": 1},
    "Patient Zero of Yesterday": {"research": 1},
    "Red Room Static": {"suppress": 1},
    "Clockwork Saint": {"contain": 1},
    "The Mirror That Interviews You": {"research": 1},
    "Basement Ocean": {"suppress": 1, "research": 1},
    # ---- ACW (Antimemetic Cold War) ----
    "ACW Unwritten Treaty Anomaly": {"research": 1},
    "ACW Cipher Hospital Anomaly": {"research": 1},
    # ---- KBO (Keter Blackout) ----
    "KBO Last Shepherd Anomaly": {"contain": 1, "suppress": 1},
    "KBO Dead Switch Anomaly": {"suppress": 1},
    # ---- ETH (Ethics Reckoning) ----
    "ETH Audit Cathedral Anomaly": {"research": 1, "contain": 1},
    "ETH Patient Sun Anomaly": {"research": 1},
    # ---- OAR (Oneiric Archives) ----
    "OAR REM Cathedral Anomaly": {"research": 1, "suppress": 1},
    "OAR Drowsing Archive Anomaly": {"research": 1},
    # ---- GOI (GOI Frontline) ----
    "GOI Hostile Benefactor Anomaly": {"suppress": 1},
    "GOI Anomalous Embassy Anomaly": {"research": 1},
}


_TASK_LABELS = {
    "research": "research",
    "contain": "containment",
    "suppress": "suppression",
}


def _format_bonus_text(bonus: dict[str, int]) -> str:
    """Render the contained-state aura as a single English sentence.

    Examples:
        {"research": 1}                  -> "While contained, your research tests get +1."
        {"contain": 1, "suppress": 1}    -> "While contained, your containment and suppression checks get +1."
        {"research": 2, "contain": 1}    -> "While contained, your research tests get +2 and your containment checks get +1."
    """
    parts: list[str] = []
    for task, amount in bonus.items():
        if amount <= 0:
            continue
        label = _TASK_LABELS.get(task, task)
        noun = "tests" if task == "research" else "checks"
        parts.append(f"your {label} {noun} get +{amount}")
    if not parts:
        return ""
    if len(parts) == 1:
        body = parts[0]
    elif len(parts) == 2:
        body = f"{parts[0]} and {parts[1]}"
    else:
        body = ", ".join(parts[:-1]) + f", and {parts[-1]}"
    return f"While contained, {body}."


def apply_contained_auras(cards: "dict[str, CardDefinition]") -> None:
    """Wire ``scp_contained_bonus`` on the assigned anomalies.

    Mutates the shared ``CardDefinition`` instances in-place. Safe to call
    multiple times (idempotent: re-running re-assigns the same dict and
    re-appends the same sentence only once because we guard the text edit).
    """
    for name, bonus in CONTAINED_BONUSES.items():
        card = cards.get(name)
        if card is None:
            # Card not found in pool — silently skip; tests will catch a
            # truly missing name via the explicit fixture-level assert.
            continue
        # Set/replace the contained-state bonus dict.
        card.scp_contained_bonus = dict(bonus)
        # Append the aura sentence to card.text once. The marker phrase
        # "While contained," is unique enough to guard against double-append
        # under repeated apply_all_mechanics() invocations.
        suffix = _format_bonus_text(bonus)
        if not suffix:
            continue
        existing = card.text or ""
        if "While contained," in existing:
            continue
        joiner = " " if existing and not existing.endswith(" ") else ""
        card.text = f"{existing}{joiner}{suffix}".strip()
