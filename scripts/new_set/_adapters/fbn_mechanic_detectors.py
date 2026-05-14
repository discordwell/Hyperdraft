"""Mechanic detectors for Foundations Beyond (FBN).

Plugs into ``scp_tournament_adapter.py`` via its ``--mechanic-map`` flag.
Each detector takes ``(state, event)`` and returns ``True`` if the event
represents the mechanic firing.

Two new FBN EventTypes were registered in Stage 4.7 (``SCP_CONTROL_SWAP``
and ``SCP_PHYLACTERY_AUDIT_OFFER``); those give us free explicit
detection for Compleation Vector swaps and Phylactery Audit offers.

The other six new mechanics (Spark Containment, Leyline Saturation,
Planar Rift, Dragon Hoard, Annihilation Wave, Wurm Devourer) ride on
existing EventTypes plus state-time mod_fns. Their detection happens via
the source GameObject's card_def carrying the relevant ``scp_*``
attribute when the event fires — we walk that in each detector.
"""
from __future__ import annotations

from typing import Any

from src.engine.types import Event, EventType


def _src_card_def(state: Any, event: Event):
    """Return the ``CardDefinition`` of the event's source, or None."""
    sid = getattr(event, "source", None)
    if not sid:
        return None
    obj = state.objects.get(sid) if hasattr(state, "objects") else None
    if obj is None:
        return None
    return getattr(obj, "card_def", None)


def _detect_compleation_vector(state: Any, event: Event) -> bool:
    """A Compleation Vector card succeeded in swapping a personnel's
    controller. Fires once per swap.
    """
    return event.type == EventType.SCP_CONTROL_SWAP


def _detect_phylactery_audit(state: Any, event: Event) -> bool:
    """A Phylactery Audit offer was issued — card recurred from
    ``scp_forgotten`` to dossier queue.
    """
    return event.type == EventType.SCP_PHYLACTERY_AUDIT_OFFER


def _detect_spark_containment(state: Any, event: Event) -> bool:
    """A Spark Containment carrier's controller successfully contained an
    opposing anomaly. We detect via SCP_CONTAINED whose context controller
    matches the containing player AND a Spark Containment carrier is on
    that side.
    """
    if event.type != EventType.SCP_CONTAINED:
        return False
    contained_by = getattr(event, "controller", None)
    if not contained_by or not hasattr(state, "objects"):
        return False
    # Walk the containing player's battlefield for a Spark Containment carrier.
    for obj in state.objects.values():
        if getattr(obj, "controller", None) != contained_by:
            continue
        cdef = getattr(obj, "card_def", None)
        if cdef is None:
            continue
        if getattr(cdef, "scp_spark_containment", 0):
            return True
    return False


def _detect_leyline_saturation(state: Any, event: Event) -> bool:
    """An opposing player opened a procedure/facility/mandate dossier
    while a Leyline Saturation anomaly was on our side.
    """
    if event.type != EventType.SCP_OPEN_DOSSIER:
        return False
    opener = getattr(event, "controller", None)
    if not opener or not hasattr(state, "objects"):
        return False
    # Look for any Leyline Saturation anomaly NOT controlled by the opener.
    for obj in state.objects.values():
        if getattr(obj, "controller", None) == opener:
            continue
        cdef = getattr(obj, "card_def", None)
        if cdef is None:
            continue
        if getattr(cdef, "scp_leyline_saturation", 0):
            return True
    return False


def _detect_planar_rift(state: Any, event: Event) -> bool:
    """A Planar Rift cascade fired: the contained card carries the
    ``scp_planar_rift`` attribute.
    """
    if event.type != EventType.SCP_CONTAINED:
        return False
    cdef = _src_card_def(state, event)
    return cdef is not None and bool(getattr(cdef, "scp_planar_rift", 0))


def _detect_dragon_hoard(state: Any, event: Event) -> bool:
    """A Dragon Hoard payoff fired: archive-gained event for a player who
    has ≥1 archived Dragon-subtype card with ``scp_dragon_hoard``.

    Heuristic — we count "fires" each time a hoard-card-holding player
    gains an archive. Doesn't tell us the bonus was *used* on a test,
    only that the hoard exists + activity is happening.
    """
    if event.type != EventType.SCP_ARCHIVE_GAINED:
        return False
    pid = (event.payload or {}).get("player")
    if not pid or not hasattr(state, "scp_sites"):
        return False
    archived = state.scp_sites.get(pid, {}).get("archives_list", [])
    return any(
        getattr(getattr(c, "card_def", None), "scp_dragon_hoard", 0)
        for c in archived
    )


def _detect_annihilation_wave(state: Any, event: Event) -> bool:
    """Annihilation Wave fired: BREACH_TICK from an anomaly whose
    ``scp_annihilation_wave`` is set.
    """
    if event.type != EventType.SCP_BREACH_TICK:
        return False
    cdef = _src_card_def(state, event)
    return cdef is not None and bool(getattr(cdef, "scp_annihilation_wave", 0))


def _detect_wurm_devourer(state: Any, event: Event) -> bool:
    """Wurm Devourer triggered: SCP_TEST_RUN succeeded on a Wurm
    Devourer anomaly.
    """
    if event.type != EventType.SCP_TEST_RUN:
        return False
    if (event.payload or {}).get("result") != "success":
        return False
    cdef = _src_card_def(state, event)
    return cdef is not None and bool(getattr(cdef, "scp_wurm_devourer", False))


FBN_MECHANIC_DETECTORS: dict[str, callable] = {
    "Compleation Vector": _detect_compleation_vector,
    "Phylactery Audit":   _detect_phylactery_audit,
    "Spark Containment":  _detect_spark_containment,
    "Leyline Saturation": _detect_leyline_saturation,
    "Planar Rift":        _detect_planar_rift,
    "Dragon Hoard":       _detect_dragon_hoard,
    "Annihilation Wave":  _detect_annihilation_wave,
    "Wurm Devourer":      _detect_wurm_devourer,
}
