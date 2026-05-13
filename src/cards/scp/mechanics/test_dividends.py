"""On-test payoffs and penalties for research-flavored SCP anomalies.

Each entry below sets ``scp_on_test`` (success hook) and optionally
``scp_on_test_fail`` (failure hook) on a card. Both hooks share the
``(obj, state) -> list[Event]`` signature consumed by ``run_test`` in
``src/engine/scp.py``. The hooks are stateless: they mutate the
controller's site dict (and, for cognitive-load cards, exhaust an extra
researcher) and return events for the pipeline to log.

Mechanic vocabulary
-------------------
- **Research bounty** — extra archive on success (``scp.gain_archives``).
- **Briefing token** — ``site["briefing"] += 1`` on success.
- **Secrecy reward** — ``site["secrecy"] += 1`` on success.
- **Risk leak** — ``site["secrecy"] -= 1`` on failure (on top of the
  engine's default secrecy hit).
- **Breach punish** — ``site["breach"] += 1`` on failure (on top of the
  hazard-based leak the engine already applies).
- **Ethics offset** — ``site["ethics_debt"] = max(0, debt - 1)`` on
  success (a small clean-up reward for studied research).
- **Self-cleanup** — ``site["breach"] = max(0, breach - 1)`` on success.
- **Cognitive load** — on success, also exhaust ONE additional friendly
  active personnel that was NOT already exhausted, modelling the
  psychic cost of the test on a witness. Pairs with a separate payoff.

The mechanic is intentionally additive on top of the engine's baseline
test resolution: success already gives +1 archive and failure already
costs secrecy + hazard-scaled breach, so these hooks only sweeten or
sharpen the existing curve.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from src.engine import scp
from src.engine.types import Event, EventType, GameObject, GameState, ZoneType

if TYPE_CHECKING:
    from src.engine.types import CardDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _site_event(event_type: EventType, obj: GameObject, **payload) -> Event:
    payload.setdefault("player", obj.controller)
    return Event(type=event_type, payload=payload, source=obj.id, controller=obj.controller)


def _active_friendly_personnel(state: GameState, player_id: str) -> list[GameObject]:
    """Return active, non-exhausted personnel for ``player_id`` on the battlefield."""
    out: list[GameObject] = []
    for pid in list(state.scp_personnel.get(player_id, [])):
        person = state.objects.get(pid)
        if not person:
            continue
        if person.zone != ZoneType.BATTLEFIELD:
            continue
        if person.state.scp_status != "active":
            continue
        if person.state.scp_exhausted:
            continue
        out.append(person)
    return out


# ---------------------------------------------------------------------------
# Success-hook factories
# ---------------------------------------------------------------------------


def _research_bounty() -> Callable[[GameObject, GameState], list[Event]]:
    """+1 archive on success (the engine already grants +1, this adds another)."""

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["archives"] += 1
        return [_site_event(
            EventType.SCP_ARCHIVE_GAINED,
            obj,
            amount=1,
            archives=s["archives"],
            reason="research_bounty",
        )]

    return hook


def _briefing_token() -> Callable[[GameObject, GameState], list[Event]]:
    """+1 briefing token on success."""

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["briefing"] += 1
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="briefing_token",
            briefing=s["briefing"],
        )]

    return hook


def _secrecy_reward() -> Callable[[GameObject, GameState], list[Event]]:
    """+1 secrecy on success."""

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["secrecy"] += 1
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="secrecy_reward",
            secrecy=s["secrecy"],
        )]

    return hook


def _ethics_offset() -> Callable[[GameObject, GameState], list[Event]]:
    """Reduce ethics_debt by 1 on success (floored at 0)."""

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        before = s["ethics_debt"]
        s["ethics_debt"] = max(0, before - 1)
        return [_site_event(
            EventType.SCP_ETHICS_SPENT,
            obj,
            reason="ethics_offset",
            amount=before - s["ethics_debt"],
            mode="research_offset",
            ethics_debt=s["ethics_debt"],
        )]

    return hook


def _self_cleanup() -> Callable[[GameObject, GameState], list[Event]]:
    """-1 breach on success (floored at 0)."""

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        before = s["breach"]
        s["breach"] = max(0, before - 1)
        return [_site_event(
            EventType.SCP_BREACH_TICK,
            obj,
            reason="research_self_cleanup",
            amount=-(before - s["breach"]),
            breach=s["breach"],
        )]

    return hook


def _research_skill(p: GameObject) -> int:
    skills = getattr(p.card_def, "scp_skills", {}) if p.card_def else {}
    return int(skills.get("research", 0) or 0)


def _resolve_cognitive_load(obj: GameObject, victim_id: str, state: GameState) -> list[Event]:
    """Exhaust ``victim_id`` and emit the cognitive-load tag event."""
    victim = state.objects.get(victim_id)
    if victim is None:
        return []
    victim.state.scp_exhausted = True
    return [_site_event(
        EventType.SCP_ASSIGN_STAFF,
        obj,
        reason="cognitive_load",
        staff_ids=[victim.id],
        task="research",
    )]


def _cognitive_load(payoff: Callable[[GameObject, GameState], list[Event]]):
    """Combine a payoff with the player choosing one extra researcher to exhaust.

    Migrated to PendingChoice — was lowest-research auto-pick. AI preserves
    the original target via ``heuristic_pick``; humans choose which body
    pays the psychic cost. Iteration-order ties stay deterministic so
    existing tests that exercise specific researchers keep working.
    """

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        events = list(payoff(obj, state) or [])
        candidates = _active_friendly_personnel(state, obj.controller)
        if not candidates:
            return events

        from src.engine.pending_choice_helpers import create_choice_and_resolve

        best = min(candidates, key=_research_skill)
        options = [
            {
                "id": p.id,
                "label": getattr(p.card_def, "name", p.id) if p.card_def else p.id,
                "description": f"Research {_research_skill(p)}",
            }
            for p in candidates
        ]

        def _resolve_handler(choice, selected, st):
            target_id = selected[0] if selected else best.id
            if isinstance(target_id, dict):
                target_id = target_id.get("id", best.id)
            return _resolve_cognitive_load(obj, target_id, st)

        events.extend(create_choice_and_resolve(
            state,
            choice_type="target",
            player_id=obj.controller,
            prompt="Cognitive load: exhaust which of your researchers?",
            options=options,
            source_id=obj.id,
            min_choices=1,
            max_choices=1,
            handler=_resolve_handler,
            heuristic_pick=[best.id],
        ))
        return events

    return hook


# ---------------------------------------------------------------------------
# Failure-hook factories
# ---------------------------------------------------------------------------


def _breach_punish(amount: int = 1) -> Callable[[GameObject, GameState], list[Event]]:
    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["breach"] += amount
        return [_site_event(
            EventType.SCP_BREACH_TICK,
            obj,
            reason="research_failure_breach",
            amount=amount,
            breach=s["breach"],
        )]

    return hook


def _risk_leak(amount: int = 1) -> Callable[[GameObject, GameState], list[Event]]:
    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["secrecy"] -= amount
        return [_site_event(
            EventType.SCP_AUDIT,
            obj,
            actor=obj.id,
            target=obj.controller,
            exposure=amount,
            reason="research_failure_leak",
        )]

    return hook


# ---------------------------------------------------------------------------
# Card-to-mechanic assignment
# ---------------------------------------------------------------------------
#
# Each tuple is ``(name, success_hook_factory, optional_fail_hook_factory, new_text)``.
# Names that do not appear in the card pool at registration time are
# silently skipped so this module is robust to set additions/removals.

_ASSIGNMENTS: tuple[
    tuple[
        str,
        Callable[[], Callable[[GameObject, GameState], list[Event]]],
        Optional[Callable[[], Callable[[GameObject, GameState], list[Event]]]],
        str,
    ],
    ...,
] = (
    # --- Core anomalies ---
    (
        "Singing Vending Machine",
        _research_bounty,
        None,
        "When you successfully research Singing Vending Machine, archives +1 (in addition to the test reward).",
    ),
    (
        "Hostile Nursery Rhyme",
        _secrecy_reward,
        lambda: _breach_punish(1),
        "When you successfully research Hostile Nursery Rhyme, secrecy +1. If the test fails, breach +1.",
    ),
    (
        "The Mirror That Interviews You",
        lambda: _cognitive_load(_research_bounty()),
        None,
        "When you successfully research The Mirror That Interviews You, archives +1, then exhaust one other active researcher.",
    ),
    (
        "Oracle Mold",
        _ethics_offset,
        None,
        "When you successfully research Oracle Mold, reduce ethics debt by 1.",
    ),
    (
        "Antimemetic Orchard",
        _secrecy_reward,
        lambda: _risk_leak(1),
        "When you successfully research Antimemetic Orchard, secrecy +1. If the test fails, secrecy -1.",
    ),
    (
        "Red Room Static",
        lambda: _cognitive_load(_secrecy_reward()),
        None,
        "When you successfully research Red Room Static, secrecy +1, then exhaust one other active researcher.",
    ),
    (
        "Patient Zero of Yesterday",
        lambda: _cognitive_load(_briefing_token()),
        lambda: _breach_punish(1),
        "When you successfully research Patient Zero of Yesterday, briefing +1, then exhaust one other active researcher. If the test fails, breach +1.",
    ),
    (
        "Paperclip Colony",
        _briefing_token,
        lambda: _breach_punish(1),
        "When you successfully research Paperclip Colony, briefing +1. If the test fails, breach +1.",
    ),
    (
        "Moth in the Camera",
        _research_bounty,
        None,
        "When you successfully research Moth in the Camera, archives +1.",
    ),
    (
        "Borrowed Moon",
        _secrecy_reward,
        None,
        "When you successfully research Borrowed Moon, secrecy +1.",
    ),
    (
        "Recursive Hallway",
        _self_cleanup,
        lambda: _breach_punish(1),
        "When you successfully research Recursive Hallway, breach -1. If the test fails, breach +1.",
    ),
    # --- ACW (Antimemetic Cold War) anomalies ---
    (
        "ACW Blind Library Anomaly",
        _research_bounty,
        None,
        "When you successfully research the Blind Library, archives +1.",
    ),
    (
        "ACW Forgotten Embassy Anomaly",
        _secrecy_reward,
        None,
        "When you successfully research the Forgotten Embassy, secrecy +1.",
    ),
    (
        "ACW Static Pilgrim Anomaly",
        _briefing_token,
        None,
        "When you successfully research the Static Pilgrim, briefing +1.",
    ),
    (
        "ACW Ghost Ledger Anomaly",
        _ethics_offset,
        None,
        "When you successfully research the Ghost Ledger, reduce ethics debt by 1.",
    ),
    (
        "ACW Hollow Survey Anomaly",
        _research_bounty,
        lambda: _risk_leak(1),
        "When you successfully research the Hollow Survey, archives +1. If the test fails, secrecy -1.",
    ),
    # --- OAR (Oneiric Archives) anomalies ---
    (
        "OAR Sleeping Observatory Anomaly",
        _briefing_token,
        None,
        "When you successfully research the Sleeping Observatory, briefing +1.",
    ),
    (
        "OAR Dream Cartographer Anomaly",
        _research_bounty,
        None,
        "When you successfully research the Dream Cartographer, archives +1.",
    ),
    (
        "OAR Velvet Alarm Anomaly",
        _secrecy_reward,
        lambda: _risk_leak(1),
        "When you successfully research the Velvet Alarm, secrecy +1. If the test fails, secrecy -1.",
    ),
    (
        "OAR Murmur Lake Anomaly",
        _ethics_offset,
        None,
        "When you successfully research Murmur Lake, reduce ethics debt by 1.",
    ),
    (
        "OAR Imaginary Elevator Anomaly",
        _self_cleanup,
        None,
        "When you successfully research the Imaginary Elevator, breach -1.",
    ),
    (
        "OAR Unremembered Morning Anomaly",
        _briefing_token,
        lambda: _risk_leak(1),
        "When you successfully research the Unremembered Morning, briefing +1. If the test fails, secrecy -1.",
    ),
    # --- ETH (Ethics Reckoning) anomalies ---
    (
        "ETH Mercy Ledger Anomaly",
        _ethics_offset,
        None,
        "When you successfully research the Mercy Ledger, reduce ethics debt by 1.",
    ),
    (
        "ETH Confession Engine Anomaly",
        _ethics_offset,
        lambda: _breach_punish(1),
        "When you successfully research the Confession Engine, reduce ethics debt by 1. If the test fails, breach +1.",
    ),
    (
        "ETH Burden Archive Anomaly",
        _research_bounty,
        lambda: _breach_punish(1),
        "When you successfully research the Burden Archive, archives +1. If the test fails, breach +1.",
    ),
    # --- GOI (Frontline) anomalies ---
    (
        "GOI Counterfeit Oracle Anomaly",
        _secrecy_reward,
        lambda: _risk_leak(1),
        "When you successfully research the Counterfeit Oracle, secrecy +1. If the test fails, secrecy -1.",
    ),
    (
        "GOI Quiet Defector Anomaly",
        _briefing_token,
        None,
        "When you successfully research the Quiet Defector, briefing +1.",
    ),
    # --- KBO (Keter Blackout) anomalies ---
    (
        "KBO Twelve-Minute God Anomaly",
        _research_bounty,
        lambda: _breach_punish(1),
        "When you successfully research the Twelve-Minute God, archives +1. If the test fails, breach +1.",
    ),
    (
        "KBO Stormward Gate Anomaly",
        _self_cleanup,
        lambda: _breach_punish(1),
        "When you successfully research the Stormward Gate, breach -1. If the test fails, breach +1.",
    ),
    (
        "KBO Crisis Glass Anomaly",
        _briefing_token,
        lambda: _breach_punish(1),
        "When you successfully research the Crisis Glass, briefing +1. If the test fails, breach +1.",
    ),
)


def apply_test_dividends(cards: "dict[str, CardDefinition]") -> None:
    """Wire ``scp_on_test`` / ``scp_on_test_fail`` for research-flavored anomalies.

    Idempotent: writing the same hook factory's output to the same
    card multiple times yields identical behaviour. Card-def instances
    are shared across in-game copies; the engine reads the attribute
    each time ``run_test`` resolves, so post-construction mutation here
    is the canonical pattern.
    """
    for name, success_factory, fail_factory, text in _ASSIGNMENTS:
        card = cards.get(name)
        if card is None:
            continue
        card.scp_on_test = success_factory()
        if fail_factory is not None:
            card.scp_on_test_fail = fail_factory()
        existing = card.text or ""
        # Idempotent: skip if our marker is already in the text.
        if text in existing:
            continue
        # Compose rather than overwrite so sibling mechanics (e.g., W2's
        # "While contained, ..." aura sentence) survive when both target
        # the same card.
        if existing.strip():
            card.text = f"{existing.rstrip()} {text}"
        else:
            card.text = text
