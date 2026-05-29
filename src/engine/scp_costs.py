"""Cost grammar + value hints for SCP activated / modal abilities.

SCP has no first-class "cost" concept — the one existing activated ability
(Mnestic Wake) hardcodes its cost in a ``precondition_fn`` and mutates the
site dict by hand. This module makes costs declarative so the dispatcher
(``scp.activate_ability``), the legal-action surface, the serializer, and the
AI all read the same spec.

``SCPCost`` spends the per-player *site* resources (see ``scp._site_defaults``)
and/or exhausts the source. ``SCPValueHint`` lets a card declare, at authoring
time, what an effect is worth in site-resource space so the heuristic AI can
value it without parsing the effect (see ``src/ai/scp_adapter.py``).

IMPORTANT — the ethics inversion: ``ethics_debt`` is a *liability* (you LOSE at
8+). "Pay N ethics" therefore means *reduce* ``ethics_debt`` by N and requires
``ethics_debt >= N`` — it is NOT a resource you accumulate. This mirrors the
shipped Mnestic Wake behaviour (``mnestic_reset/helpers.py``). Get this
backwards and a "cost" would heal the player.

This module imports ``scp`` lazily (inside functions) to avoid an import cycle
(``scp`` imports ``activate_ability`` which uses this module).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# Site resources a cost can spend. ``ethics`` is the inverted one (reduces debt).
# discard / sacrifice are declared for forward-compat but not yet payable — the
# Phase-0 canaries don't need them; wiring them lands in Phase 2.
@dataclass(frozen=True)
class SCPCost:
    ethics: int = 0        # reduce ethics_debt by N (requires debt >= N)
    secrecy: int = 0       # spend secrecy (requires secrecy >= N)
    briefing: int = 0      # spend briefing (requires briefing >= N)
    clearance: int = 0     # spend clearance (requires clearance >= N)
    archives: int = 0      # spend archives (requires archives >= N)
    exhaust_self: bool = False   # requires source un-exhausted; exhausts it
    discard: int = 0       # Phase 2 — NotImplementedError if used
    sacrifice_self: bool = False  # Phase 2 — NotImplementedError if used

    def is_free(self) -> bool:
        return not (
            self.ethics or self.secrecy or self.briefing or self.clearance
            or self.archives or self.exhaust_self or self.discard or self.sacrifice_self
        )


# Signed deltas an effect produces, in site-resource space, plus a few board
# flags. Negative breach / ethics_debt = good (reduces a loss clock). The AI's
# estimator (Phase 3) turns this into a scalar using the same weights it already
# encodes for breach danger / alt-win proximity.
@dataclass(frozen=True)
class SCPValueHint:
    breach: int = 0
    secrecy: int = 0
    archives: int = 0
    briefing: int = 0
    clearance: int = 0
    ethics_debt: int = 0
    gains_mnestic: bool = False
    contains_anomaly: bool = False
    steals_permanent: bool = False
    custom_value_fn: Optional[Callable[[Any, Any, Optional[str]], float]] = None

    def is_trivial(self) -> bool:
        """True if the hint carries no signal — the AI would never fire it.

        Used by the test-interceptors extension to flag "ability registered but
        value_hint all-zero" (the SCP analogue of an empty effect_fn stub).
        """
        return (
            not any((self.breach, self.secrecy, self.archives, self.briefing,
                     self.clearance, self.ethics_debt))
            and not (self.gains_mnestic or self.contains_anomaly or self.steals_permanent)
            and self.custom_value_fn is None
        )


def _site(state, player_id: str) -> dict:
    from src.engine import scp  # lazy — avoid import cycle with scp.activate_ability
    return scp.site(state, player_id)


def can_pay_scp_cost(obj, state, cost: SCPCost) -> tuple[bool, str]:
    """Whether ``obj``'s controller can pay ``cost`` right now. Read-only."""
    if cost.discard or cost.sacrifice_self:
        raise NotImplementedError(
            "SCPCost.discard / sacrifice_self are Phase-2; not yet payable."
        )
    site = _site(state, obj.controller)
    if cost.ethics and int(site.get("ethics_debt", 0) or 0) < cost.ethics:
        return False, f"Need {cost.ethics} ethics debt to pay down"
    if cost.secrecy and int(site.get("secrecy", 0) or 0) < cost.secrecy:
        return False, f"Need {cost.secrecy} secrecy"
    if cost.briefing and int(site.get("briefing", 0) or 0) < cost.briefing:
        return False, f"Need {cost.briefing} briefing"
    if cost.clearance and int(site.get("clearance", 0) or 0) < cost.clearance:
        return False, f"Need {cost.clearance} clearance"
    if cost.archives and int(site.get("archives", 0) or 0) < cost.archives:
        return False, f"Need {cost.archives} archives"
    if cost.exhaust_self and bool(getattr(obj.state, "scp_exhausted", False)):
        return False, "Source is exhausted"
    return True, ""


def pay_scp_cost(game, obj, cost: SCPCost) -> list:
    """Pay ``cost`` (mutates the site dict / exhausts the source). No validation
    here — call ``can_pay_scp_cost`` first. Returns log events (currently none;
    the resource mutation is observable in the serialized site state)."""
    if cost.discard or cost.sacrifice_self:
        raise NotImplementedError(
            "SCPCost.discard / sacrifice_self are Phase-2; not yet payable."
        )
    site = _site(game.state, obj.controller)
    if cost.ethics:
        site["ethics_debt"] = int(site.get("ethics_debt", 0) or 0) - cost.ethics
    if cost.secrecy:
        site["secrecy"] = int(site.get("secrecy", 0) or 0) - cost.secrecy
    if cost.briefing:
        site["briefing"] = int(site.get("briefing", 0) or 0) - cost.briefing
    if cost.clearance:
        site["clearance"] = int(site.get("clearance", 0) or 0) - cost.clearance
    if cost.archives:
        site["archives"] = int(site.get("archives", 0) or 0) - cost.archives
    if cost.exhaust_self:
        obj.state.scp_exhausted = True
    return []


def describe_scp_cost(cost: SCPCost) -> str:
    """Human-readable cost label, e.g. "Pay 1 ethics, exhaust"."""
    parts: list[str] = []
    if cost.ethics:
        parts.append(f"pay {cost.ethics} ethics")
    if cost.secrecy:
        parts.append(f"pay {cost.secrecy} secrecy")
    if cost.briefing:
        parts.append(f"pay {cost.briefing} briefing")
    if cost.clearance:
        parts.append(f"pay {cost.clearance} clearance")
    if cost.archives:
        parts.append(f"pay {cost.archives} archives")
    if cost.discard:
        parts.append(f"discard {cost.discard}")
    if cost.sacrifice_self:
        parts.append("sacrifice this")
    if cost.exhaust_self:
        parts.append("exhaust")
    if not parts:
        return "Free"
    label = ", ".join(parts)
    return label[0].upper() + label[1:]


__all__ = [
    "SCPCost",
    "SCPValueHint",
    "can_pay_scp_cost",
    "pay_scp_cost",
    "describe_scp_cost",
]
