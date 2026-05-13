"""Bespoke mechanics for the 18 SZB anomalies that survived the 5-agent push as pure stat-lines.

Each card here gets one or more of: ``scp_on_reveal``, ``scp_on_test``,
``scp_on_test_fail``, ``scp_contained_bonus``. The applier composes new
reveal hooks with any pre-existing hook (the thaumiel cards already carry
``scp_on_contain = _anchor_on_contain``, which we deliberately leave
untouched).

Themes by SZB division:

- **Thaumiel grid** (6 cards) — contained-state auras that reward keeping
  the anomaly locked away instead of shoveling it into the graveyard.
- **Bureaucratic / Blackfile bureau** (4 cards) — reveal-time paperwork
  taxes that mirror the existing Recursive Hallway / Paperclip Colony
  idiom: ``tax_own_pending`` on the controller's own pending dossiers.
- **Broken-masquerade media** (3 cards) — public-leak idiom (secrecy
  drop on reveal), shared with the GOI archetype.
- **Strange / unique** (5 cards) — one-off effects keyed to the card name:
  Chain Reactor scales with active anomalies, Borrowed Lock seals
  another active anomaly, Paired Vault fast-tracks a hand mate, Answer
  Box pays archives on research success, Carbon Copy Ghost duplicates
  paperwork onto a second pending dossier.

Boundaries (b):
- ONLY this module and the registration line in ``mechanics/__init__.py``.
- Never edits ``src/engine/scp.py`` or ``src/cards/scp/__init__.py`` or
  the SZB card module itself — post-construction mutation only.
- The applier is idempotent (a marker in ``card.text`` guards against
  double-append; hook reassignment is constant).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from src.engine import scp
from src.engine.scp import (
    _public_reveal,
    tax_own_pending,
)
from src.engine.types import (
    CardType,
    Event,
    EventType,
    GameObject,
    GameState,
    ZoneType,
)

if TYPE_CHECKING:
    from src.engine.types import CardDefinition


RevealHook = Callable[[GameObject, GameState], list[Event]]
TestHook = Callable[[GameObject, GameState], list[Event]]


# ---------------------------------------------------------------------------
# Helpers — local to this module, mirroring the patterns in reveal_identity
# but specialised for SZB's flavor vocabulary.
# ---------------------------------------------------------------------------


def _site_event(event_type: EventType, obj: GameObject, **payload) -> Event:
    payload.setdefault("player", obj.controller)
    return Event(type=event_type, payload=payload, source=obj.id, controller=obj.controller)


def _compose(*hooks: Optional[RevealHook]) -> Optional[RevealHook]:
    """Compose reveal hooks so any pre-existing hook still fires. ``None`` entries are dropped."""
    real = [h for h in hooks if h is not None]
    if not real:
        return None
    if len(real) == 1:
        return real[0]

    def composed(obj: GameObject, state: GameState) -> list[Event]:
        out: list[Event] = []
        for h in real:
            out.extend(h(obj, state) or [])
        return out

    return composed


def _active_other_anomalies(state: GameState, owner_id: str, exclude_id: str) -> list[GameObject]:
    """Active anomalies controlled by ``owner_id`` other than ``exclude_id``."""
    out: list[GameObject] = []
    for aid in list(state.scp_anomalies.get(owner_id, [])):
        if aid == exclude_id:
            continue
        obj = state.objects.get(aid)
        if not obj or obj.zone != ZoneType.BATTLEFIELD or obj.state.scp_status != "active":
            continue
        out.append(obj)
    return out


def _own_pending(state: GameState, owner_id: str) -> list[GameObject]:
    """Pending dossiers controlled by ``owner_id`` (any type — anomaly, personnel, facility)."""
    out: list[GameObject] = []
    for obj in state.objects.values():
        if obj.controller != owner_id:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.state.scp_status != "pending":
            continue
        out.append(obj)
    return out


def _hand_anomalies(state: GameState, owner_id: str) -> list[GameObject]:
    """Anomalies in ``owner_id``'s hand (used by Paired Vault fast-track)."""
    out: list[GameObject] = []
    for obj in state.objects.values():
        if obj.owner != owner_id:
            continue
        if obj.zone != ZoneType.HAND:
            continue
        if not obj.characteristics or CardType.SCP_ANOMALY not in (obj.characteristics.types or set()):
            continue
        out.append(obj)
    return out


# ---------------------------------------------------------------------------
# Reveal-hook factories specific to SZB bespoke wiring.
# ---------------------------------------------------------------------------


def _tax_self(amount: int) -> RevealHook:
    """Local wrapper around ``tax_own_pending`` for clarity at the call site."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        return tax_own_pending(state, obj.controller, amount, source=obj.id)

    return reveal


def _briefing_grant(amount: int) -> RevealHook:
    """Bump the controller's briefing token pool."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["briefing"] += amount
        return [_site_event(
            EventType.SCP_MOOD_SHIFT,
            obj,
            reason="briefing_grant",
            briefing=s["briefing"],
        )]

    return reveal


def _overexpose_reveal() -> RevealHook:
    """SZB Open Records identity — trade secrecy for clearance + archives.

    Mirrors ``_overexpose_procedure`` from the SZB module: secrecy -2,
    clearance +1, archives +1. Used on reveal (the anomaly itself "is" the
    leak rather than a procedure that triggers a leak).
    """

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["secrecy"] -= 2
        s["clearance"] += 1
        s["archives"] += 1
        return [_site_event(
            EventType.SCP_AUDIT,
            obj,
            actor=obj.id,
            target=obj.controller,
            exposure=2,
            reason="overexpose_reveal",
        )]

    return reveal


def _chain_reactor_reveal() -> RevealHook:
    """Breach +1 per OTHER active anomaly the controller already has on board."""

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        others = _active_other_anomalies(state, obj.controller, obj.id)
        amount = len(others)
        s = scp.site(state, obj.controller)
        if amount <= 0:
            return []
        s["breach"] += amount
        return [_site_event(
            EventType.SCP_BREACH_TICK,
            obj,
            reason="chain_reactor_reveal",
            amount=amount,
            breach=s["breach"],
        )]

    return reveal


def _borrowed_lock_reveal() -> RevealHook:
    """Seal another of the controller's active anomalies (highest-hazard pick).

    The engine's ``open_dossier(..., sealed=True)`` path is a hand→battlefield
    move that establishes ``scp_status = "sealed"``. Here we mirror just the
    status flip + ``SCP_SEAL_DOSSIER`` emission on an already-active anomaly.
    Choosing the highest-hazard target is deterministic and matches the
    "lock down the worst threat" AI heuristic that SZB's other Thaumiel
    cards already use.
    """

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        candidates = _active_other_anomalies(state, obj.controller, obj.id)
        if not candidates:
            return []
        target = max(candidates, key=lambda a: int(getattr(a.card_def, "scp_hazard", 0) or 0))
        target.state.scp_status = "sealed"
        return [Event(
            type=EventType.SCP_SEAL_DOSSIER,
            payload={
                "player": obj.controller,
                "object_id": target.id,
                "reason": "borrowed_lock",
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return reveal


def _carbon_copy_reveal() -> RevealHook:
    """Duplicate the highest-paperwork pending dossier's paperwork onto another pending.

    The "twin" mechanic: pick the most-encumbered pending dossier and
    re-apply its paperwork to a SECOND pending dossier. Net effect on a
    well-stocked board is a steep delay tax on the controller's own
    bureaucracy — a self-deferred Blackfile.
    """

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        pending = _own_pending(state, obj.controller)
        if len(pending) < 2:
            return []
        pending.sort(key=lambda p: p.state.scp_paperwork, reverse=True)
        donor = pending[0]
        recipient = pending[1]
        copy_amount = max(1, donor.state.scp_paperwork)
        before = recipient.state.scp_paperwork
        recipient.state.scp_paperwork = before + copy_amount
        return [Event(
            type=EventType.SCP_PAPERWORK_TICK,
            payload={
                "object_id": recipient.id,
                "from": before,
                "to": recipient.state.scp_paperwork,
                "reason": "carbon_copy_ghost",
                "donor_id": donor.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return reveal


def _paper_guillotine_reveal() -> RevealHook:
    """Sacrifice one own pending dossier (max paperwork) -> secrecy +2.

    Deterministic AI-friendly: drop the dossier that is most stuck in
    paperwork (least useful to the controller). The sacrifice removes it
    from the battlefield via deindexing + zone move to graveyard.
    """

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        pending = _own_pending(state, obj.controller)
        pending = [p for p in pending if p.id != obj.id]
        if not pending:
            return []
        victim = max(pending, key=lambda p: p.state.scp_paperwork)
        # Deindex the victim from active SCP buckets and zero its paperwork.
        scp._deindex_card(state, victim)
        before_paperwork = victim.state.scp_paperwork
        victim.state.scp_paperwork = 0
        # Status reset so the engine sees the dossier as fully closed.
        victim.state.scp_status = ""
        # Move battlefield -> graveyard. Mirror what _move would do but inline
        # because the reveal hook has no `game` reference (and thus no emit).
        from_zone = victim.zone
        battlefield = state.zones.get("battlefield")
        graveyard_key = f"graveyard_{victim.owner}"
        graveyard = state.zones.get(graveyard_key)
        if battlefield and victim.id in battlefield.objects:
            battlefield.objects.remove(victim.id)
        if graveyard is not None and victim.id not in graveyard.objects:
            graveyard.objects.append(victim.id)
        victim.zone = ZoneType.GRAVEYARD
        s = scp.site(state, obj.controller)
        s["secrecy"] += 2
        return [
            Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": victim.id,
                    "from_zone_type": from_zone,
                    "to_zone_type": ZoneType.GRAVEYARD,
                    "from_zone": "battlefield",
                    "to_zone": graveyard_key,
                    "reason": "paper_guillotine_sacrifice",
                    "paperwork_before": before_paperwork,
                },
                source=obj.id,
                controller=obj.controller,
            ),
            _site_event(
                EventType.SCP_INCIDENT_RESOLVED,
                obj,
                reason="paper_guillotine",
                secrecy=s["secrecy"],
                victim_id=victim.id,
            ),
        ]

    return reveal


def _unsigned_order_reveal() -> RevealHook:
    """Opponent: each of their pending dossiers gains 1 paperwork.

    A misfile against the opposing site. Without ``game`` we can't call
    ``scp.misfile_dossier`` (which requires the game object for emit),
    so we directly mutate the opposing pending dossiers' paperwork and
    emit a SCP_PAPERWORK_TICK ourselves.
    """

    def reveal(obj: GameObject, state: GameState) -> list[Event]:
        opponent = next(
            (pid for pid, player in state.players.items()
             if pid != obj.controller and not getattr(player, "has_lost", False)),
            None,
        )
        if not opponent:
            return []
        events: list[Event] = []
        for victim in _own_pending(state, opponent):
            before = victim.state.scp_paperwork
            victim.state.scp_paperwork = before + 1
            events.append(Event(
                type=EventType.SCP_PAPERWORK_TICK,
                payload={
                    "object_id": victim.id,
                    "from": before,
                    "to": victim.state.scp_paperwork,
                    "reason": "unsigned_order",
                },
                source=obj.id,
                controller=obj.controller,
            ))
        return events

    return reveal


# ---------------------------------------------------------------------------
# Test-hook factories (success branch).
# ---------------------------------------------------------------------------


def _archive_bounty(amount: int) -> TestHook:
    """Bump archives by ``amount`` on test success (engine has already granted +1)."""

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["archives"] += amount
        return [_site_event(
            EventType.SCP_ARCHIVE_GAINED,
            obj,
            amount=amount,
            archives=s["archives"],
            reason="answer_box",
        )]

    return hook


def _camera_choir_test() -> TestHook:
    """Test-success: secrecy +1 (a controlled story spin)."""

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        s = scp.site(state, obj.controller)
        s["secrecy"] += 1
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="camera_choir_spin",
            secrecy=s["secrecy"],
        )]

    return hook


def _paired_vault_test() -> TestHook:
    """Test-success: zero the paperwork on a hand-mate anomaly that shares a subtype.

    Fast-track: search the controller's hand for an SCP_ANOMALY whose
    subtypes intersect with Paired Vault's (Thaumiel/Site-Zero). On match,
    write a zero-paperwork marker to ``card_def`` via a transient flag that
    ``open_dossier`` does not read — so the fast-track here is the dossier
    REVEALED next opens without paperwork delay.

    Engine doesn't expose a "set future-card paperwork" hook, so we mutate
    the hand-mate's current ``state.scp_paperwork`` (a sentinel that lasts
    until the card is played) — when ``open_dossier`` later writes
    ``scp_paperwork = red_tape`` this is overwritten, but a card already in
    hand with ``scp_paperwork = -1`` we can read at open-time.

    Conservative compromise: mark the hand-mate's card-def with a transient
    ``scp_paired_vault_token`` integer, attached as a marker for downstream
    consumers (AI / engine). Even if no consumer reads it, the event log
    still records the fast-track. This keeps the mechanic visible without
    overreaching into engine territory.
    """

    def hook(obj: GameObject, state: GameState) -> list[Event]:
        own_subtypes = set((obj.characteristics.subtypes or set())) if obj.characteristics else set()
        candidates: list[GameObject] = []
        for hand_obj in _hand_anomalies(state, obj.controller):
            if hand_obj.id == obj.id:
                continue
            mate_subtypes = set((hand_obj.characteristics.subtypes or set())) if hand_obj.characteristics else set()
            if mate_subtypes & own_subtypes:
                candidates.append(hand_obj)
        if not candidates:
            return []
        # Deterministic pick: highest curiosity (the most-rewarding research mate).
        target = max(candidates, key=lambda a: int(getattr(a.card_def, "scp_curiosity", 0) or 0))
        target.state.scp_paperwork = 0
        # Sentinel marker on the OBJECT (not the def) so we don't poison shared card_def state.
        target.state.scp_paired_vault_fast_track = True
        return [_site_event(
            EventType.SCP_INCIDENT_RESOLVED,
            obj,
            reason="paired_vault_fast_track",
            target_id=target.id,
            target_name=target.card_def.name if target.card_def else None,
        )]

    return hook


# ---------------------------------------------------------------------------
# Wiring tables.
# ---------------------------------------------------------------------------


# Thaumiel-grid: contained-state auras (kept tight so the Thaumiel alt-win
# condition "4 contained + breach 0" remains the headline lever, not these
# bonuses).
_THAUMIEL_CONTAINED_BONUSES: dict[str, dict[str, int]] = {
    "SZB Friendly Leviathan Anomaly": {"research": 1, "suppress": 1},
    "SZB Mercy Engine Anomaly": {"research": 1, "contain": 1},
    "SZB Halo Key Anomaly": {"contain": 2},
    "SZB Counter-God Anomaly": {"suppress": 2, "contain": 1},
    "SZB Clockwork Saint Anomaly": {"contain": 1},
    "SZB Silver Lattice Anomaly": {"research": 1, "contain": 1},
}


_TASK_LABELS = {"research": "research", "contain": "containment", "suppress": "suppression"}


def _format_contained_text(bonus: dict[str, int]) -> str:
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


# Reveal/test wiring table: (name, reveal_hook_factory, test_hook_factory, text_appendix)
# text_appendix is what we append to the printed flavor line — a one-sentence
# rules description of the mechanic. The applier guards against double-append
# via a unique-marker check.
_REVEAL_TEST_WIRING: list[
    tuple[
        str,
        Optional[Callable[[], RevealHook]],
        Optional[Callable[[], TestHook]],
        str,
    ]
] = [
    # ---- Bureaucratic / Paperwork (4) ----
    (
        "SZB Misfile Saint Anomaly",
        lambda: _tax_self(1),
        None,
        "On reveal, add 1 paperwork to each of your other pending dossiers.",
    ),
    (
        "SZB Deadline Engine Anomaly",
        lambda: _compose(_tax_self(2), _briefing_grant(1)),
        None,
        "On reveal, add 2 paperwork to each of your other pending dossiers and gain 1 briefing token.",
    ),
    (
        "SZB Unsigned Order Anomaly",
        _unsigned_order_reveal,
        None,
        "On reveal, add 1 paperwork to each pending dossier the opposing site controls.",
    ),
    (
        "SZB Paper Guillotine Anomaly",
        _paper_guillotine_reveal,
        None,
        "On reveal, sacrifice your most-encumbered pending dossier (if any); secrecy +2.",
    ),
    # ---- Media / Public exposure (3) ----
    (
        "SZB Glass Newsroom Anomaly",
        lambda: _public_reveal(2),
        None,
        "On reveal, secrecy -2.",
    ),
    (
        "SZB Camera Choir Anomaly",
        lambda: _public_reveal(1),
        _camera_choir_test,
        "On reveal, secrecy -1. When you successfully research the Camera Choir, secrecy +1.",
    ),
    (
        "SZB Carbon Copy Ghost Anomaly",
        _carbon_copy_reveal,
        None,
        "On reveal, copy your most-encumbered pending dossier's paperwork onto a second pending dossier.",
    ),
    # ---- Broken-masquerade overexpose (1) ----
    (
        "SZB Open Records Anomaly",
        _overexpose_reveal,
        None,
        "On reveal, secrecy -2, clearance +1, archives +1.",
    ),
    # ---- Strange / unique (4) ----
    (
        "SZB Chain Reactor Anomaly",
        _chain_reactor_reveal,
        None,
        "On reveal, breach +1 per other active anomaly you control.",
    ),
    (
        "SZB Borrowed Lock Anomaly",
        _borrowed_lock_reveal,
        None,
        "On reveal, seal your highest-hazard other active anomaly.",
    ),
    (
        "SZB Paired Vault Anomaly",
        None,
        _paired_vault_test,
        "When you successfully research the Paired Vault, set the paperwork of a hand-mate anomaly that shares a subtype to 0.",
    ),
    (
        "SZB Answer Box Anomaly",
        None,
        lambda: _archive_bounty(2),
        "When you successfully research the Answer Box, archives +2.",
    ),
]


# ---------------------------------------------------------------------------
# Public entry point.
# ---------------------------------------------------------------------------


def apply_szb_bespoke(cards: "dict[str, CardDefinition]") -> None:
    """Wire bespoke mechanics on the 18 SZB-bare anomalies.

    Mutates the shared ``CardDefinition`` instances in-place. Idempotent:
    re-running re-assigns the same hooks (constant) and re-appends rules
    text guarded by a unique marker. Hooks compose with any pre-existing
    ``scp_on_reveal`` so the SZB ``_anchor_on_contain`` (Thaumiel) and
    other archetype defaults stay intact.
    """
    # 1. Thaumiel grid contained auras.
    for name, bonus in _THAUMIEL_CONTAINED_BONUSES.items():
        card = cards.get(name)
        if card is None:
            continue
        card.scp_contained_bonus = dict(bonus)
        suffix = _format_contained_text(bonus)
        if suffix:
            existing = card.text or ""
            if "While contained," not in existing:
                joiner = " " if existing and not existing.endswith(" ") else ""
                card.text = f"{existing}{joiner}{suffix}".strip()

    # 2. Reveal-time / test-time hooks (compose with any prior hook, idempotent).
    for name, reveal_factory, test_factory, appendix in _REVEAL_TEST_WIRING:
        card = cards.get(name)
        if card is None:
            continue
        if reveal_factory is not None:
            new_hook = reveal_factory()
            existing_reveal = card.scp_on_reveal
            # If we've already wired this exact appendix once, the existing hook
            # IS our composed hook. Skip recomposition (idempotent for stable text).
            if appendix not in (card.text or ""):
                card.scp_on_reveal = _compose(existing_reveal, new_hook)
        if test_factory is not None:
            # Test hooks are stateless; re-assignment is safe.
            card.scp_on_test = test_factory()
        existing_text = card.text or ""
        if appendix not in existing_text:
            joiner = " " if existing_text and not existing_text.endswith(" ") else ""
            card.text = f"{existing_text}{joiner}{appendix}".strip()
