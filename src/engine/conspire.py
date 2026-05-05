"""
Shadowmoor / Lorwyn — Conspire mechanic (CR 702.78).

Reminder text:

    Conspire (As you cast this spell, you may tap two untapped creatures you
    control that share a color with it. When you do, copy it. You may choose
    new targets for the copy. A copy of a permanent spell becomes a token.)

In this codebase, Conspire never appears as printed text on a spell — it is
always *granted* by a permanent ability (e.g. Raiding Schemes:
"Each noncreature spell you cast has conspire."). The grant model means:
while a Raiding Schemes is on the battlefield, every matching spell its
controller casts gets the Conspire OPTION (not a forced trigger).

Implementation overview
-----------------------

Conspire is hooked into the cast pipeline (priority._handle_cast_spell_sync)
in a single, marked region. The flow is:

  1. After a spell has been cast (CAST event has been built and is about to
     be emitted), the priority hook scans the active conspire grants on the
     state. If one applies to the spell's controller + spell_filter, a
     PendingChoice of choice_type='conspire' is opened.

  2. The prompt offers two outcomes:
       * Decline — proceed; no copy.
       * Accept — pick two untapped creatures the caster controls that share
         a color with the spell. The two creatures are tapped via TAP
         events; a COPY_STACK_ITEM event is queued for the spell that just
         landed on the stack.

  3. The conspire copy is pushed onto the stack on top of the original spell
     (LIFO: the copy resolves first).

Auto-decline: when no human action handler is registered for the caster
(typical in tests / pure-AI runs), the conspire prompt is auto-declined so
existing tests keep their existing behavior.

Public API
----------

- ``ConspireGrant`` — dataclass: source_id, controller, spell_filter,
  color_share_required.
- ``grant_conspire(source, *, spell_filter, color_share_required=True)`` —
  installs an interceptor that registers the grant on the state and removes
  it when the source leaves the battlefield. Pair with the helper re-export
  in src/cards/interceptor_helpers.py (``make_conspire_grant``).
- ``find_conspire_grants_for_spell(state, controller, spell_obj)`` — the
  priority hook calls this to check if any active grant applies.
- ``open_conspire_prompt(...)`` — the priority hook delegates the actual
  prompt construction here.
- ``find_color_share_creatures(state, controller, spell_colors)`` — query
  helper used by tests / UI to surface legal "tap pairs" before opening
  the prompt.

Module-level constants
----------------------

- ``CONSPIRE_GRANTS_KEY`` — key on ``state.turn_data`` (acts as a process-
  durable registry; not actually a turn-scoped value, but using turn_data
  keeps it out of the typed GameState shape).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .types import (
    Color,
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    PendingChoice,
    ZoneType,
    CardType,
    new_id,
)


CONSPIRE_GRANTS_KEY = "conspire_grants"


# =============================================================================
# Grant registry
# =============================================================================


@dataclass
class ConspireGrant:
    """One active conspire grant.

    Attributes:
        grant_id: stable id (matches the installed interceptor's id).
        source_id: object id of the permanent providing the grant.
        controller: player whose spells get conspire.
        spell_filter: ``(spell_obj, state) -> bool``. Should return True
            when this grant's conspire applies to the spell about to be
            cast. Typical filters: "noncreature spell", "red or green
            instant/sorcery", "spell I control".
        color_share_required: when True (CR 702.78 default), the two
            tapped creatures must share a color with the spell. Setting
            False is reserved for future variants (e.g. fixed-pair
            conspire from custom-set designs).
    """
    grant_id: str
    source_id: str
    controller: str
    spell_filter: Callable[[GameObject, GameState], bool]
    color_share_required: bool = True


def _get_grant_registry(state: GameState) -> dict[str, ConspireGrant]:
    """Lazy-init the grant registry on ``state.turn_data``."""
    reg = state.turn_data.get(CONSPIRE_GRANTS_KEY)
    if reg is None:
        reg = {}
        state.turn_data[CONSPIRE_GRANTS_KEY] = reg
    return reg


def _register_grant(state: GameState, grant: ConspireGrant) -> None:
    _get_grant_registry(state)[grant.grant_id] = grant


def _unregister_grant(state: GameState, grant_id: str) -> None:
    reg = state.turn_data.get(CONSPIRE_GRANTS_KEY)
    if isinstance(reg, dict):
        reg.pop(grant_id, None)


def list_active_grants(state: GameState) -> list[ConspireGrant]:
    """Return all currently active conspire grants (used by the priority hook).

    Lazily prunes any registry entries whose source has left the
    battlefield. This belt-and-braces with the interceptor-based cleanup
    so callers always see a fresh view.
    """
    reg = state.turn_data.get(CONSPIRE_GRANTS_KEY)
    if not isinstance(reg, dict):
        return []
    # Prune stale entries (source no longer on battlefield).
    stale_ids: list[str] = []
    for gid, grant in reg.items():
        src = state.objects.get(grant.source_id)
        if src is None or src.zone != ZoneType.BATTLEFIELD:
            stale_ids.append(gid)
    for gid in stale_ids:
        reg.pop(gid, None)
    return list(reg.values())


# =============================================================================
# Lookups
# =============================================================================


def find_conspire_grants_for_spell(
    state: GameState,
    controller: str,
    spell_obj: GameObject,
) -> list[ConspireGrant]:
    """Return all grants whose source is on the battlefield and whose filter
    accepts ``spell_obj`` cast by ``controller``.

    Per CR 702.78, multiple grants on the same spell each give an
    independent conspire OPTION, but conspire is "may" so a player only
    chooses to use one (or none) per spell. We return the full match list
    so the priority hook can pick the most permissive (or just the first)
    grant when opening the prompt.
    """
    out: list[ConspireGrant] = []
    for grant in list_active_grants(state):
        if grant.controller != controller:
            continue
        # Source must still exist on the battlefield (graveyard / exile
        # would already have triggered our cleanup, but check defensively).
        src = state.objects.get(grant.source_id)
        if src is None or src.zone != ZoneType.BATTLEFIELD:
            # Cleanup stale registry entry.
            _unregister_grant(state, grant.grant_id)
            continue
        try:
            ok = bool(grant.spell_filter(spell_obj, state))
        except Exception:
            ok = False
        if ok:
            out.append(grant)
    return out


def find_color_share_creatures(
    state: GameState,
    controller: str,
    spell_colors: set[Color],
) -> list[GameObject]:
    """Return untapped creatures the caster controls that share at least one
    color with ``spell_colors``.

    Colorless spells share NO colors with anything (per CR 702.78 reading;
    "share a color" requires both sides to have at least one matching
    color). A spell with no colors offers no legal conspire pair.
    """
    if not spell_colors:
        return []
    out: list[GameObject] = []
    for obj in state.objects.values():
        if obj.controller != controller:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        if obj.state.tapped:
            continue
        creature_colors = set(obj.characteristics.colors or set())
        if creature_colors & spell_colors:
            out.append(obj)
    return out


# =============================================================================
# Grant installation
# =============================================================================


def grant_conspire(
    source: GameObject,
    state: GameState,
    *,
    spell_filter: Callable[[GameObject, GameState], bool],
    color_share_required: bool = True,
) -> Interceptor:
    """Install a "Each <filtered spell> you cast has conspire" effect.

    Args:
        source: the permanent providing the grant (Raiding Schemes,
            Wort, the Raidmother). Conspire applies while ``source`` is on
            the battlefield; it auto-removes when ``source`` leaves.
        state: GameState — used to register the grant on the runtime
            registry stash (turn_data['conspire_grants']).
        spell_filter: ``(spell_obj, state) -> bool``. Common patterns:
            * Noncreature: ``CardType.CREATURE not in spell.characteristics.types``
            * Red or green instant/sorcery: type intersection + color check.
        color_share_required: when True, the cast hook enforces "two
            untapped creatures sharing a color with the spell" (CR 702.78).
            Currently always True; the parameter is reserved for future
            custom-set variants.

    Returns the installed Interceptor. The interceptor only watches for
    ZONE_CHANGE on the source so the registry entry can be cleaned up when
    the source leaves the battlefield. The actual cast-time prompt is
    driven from priority._handle_cast_spell_sync.
    """
    grant_id = new_id()

    grant = ConspireGrant(
        grant_id=grant_id,
        source_id=source.id,
        controller=source.controller,
        spell_filter=spell_filter,
        color_share_required=color_share_required,
    )
    # Register the grant on the runtime registry immediately so the cast
    # pipeline can find it on the very next CAST.
    _register_grant(state, grant)

    def _filter(event: Event, state: GameState) -> bool:
        # We listen for ZONE_CHANGE on the source so we can self-clean
        # the registry entry. (The cast pipeline drives the actual
        # conspire prompt — no per-cast event fires through the
        # interceptor system here.)
        if event.type != EventType.ZONE_CHANGE:
            return False
        return event.payload.get('object_id') == source.id

    def _handler(event: Event, state: GameState) -> InterceptorResult:
        # If the source is leaving the battlefield, remove the grant.
        # ZONE_CHANGE has both keys: 'from_zone'/'to_zone' (string keys
        # like "battlefield" / "graveyard_p1") and 'from_zone_type' /
        # 'to_zone_type' (ZoneType enums). We accept either form so we
        # handle both directly-emitted and pipeline-normalised events.
        from_zt = event.payload.get('from_zone_type') or event.payload.get('from_zone')
        to_zt = event.payload.get('to_zone_type') or event.payload.get('to_zone')

        def _is_battlefield(z: Any) -> bool:
            # Accept ZoneType.BATTLEFIELD or any string starting with
            # "battlefield" (e.g. "battlefield" the shared zone key).
            if z is ZoneType.BATTLEFIELD:
                return True
            if hasattr(z, 'name') and getattr(z, 'name', '').lower() == 'battlefield':
                return True
            return isinstance(z, str) and z.lower().startswith('battlefield')

        if _is_battlefield(from_zt) and not _is_battlefield(to_zt):
            _unregister_grant(state, grant_id)
        return InterceptorResult(action=InterceptorAction.PASS)

    interceptor = Interceptor(
        id=grant_id,
        source=source.id,
        controller=source.controller,
        priority=InterceptorPriority.REACT,
        filter=_filter,
        handler=_handler,
        duration='while_on_battlefield',
    )

    # Store grant lookup data on the interceptor so external code that
    # iterates ``state.interceptors`` (debug dumps, UI labels) can identify
    # this as a conspire grant without scanning turn_data.
    setattr(interceptor, '_conspire_grant', grant)

    return interceptor


# =============================================================================
# Cast-pipeline integration (called from priority._handle_cast_spell_sync)
# =============================================================================


CONSPIRE_HANDLED_FLAG = "conspire_handled"


def _conspire_handled_key(spell_id: str) -> str:
    return f"{CONSPIRE_HANDLED_FLAG}:{spell_id}"


def mark_conspire_handled(state: GameState, spell_id: str) -> None:
    """Record that this spell already passed through the conspire hook
    (so re-entry from a continuation doesn't re-prompt)."""
    if not spell_id:
        return
    state.turn_data[_conspire_handled_key(spell_id)] = True


def is_conspire_handled(state: GameState, spell_id: str) -> bool:
    if not spell_id:
        return False
    return bool(state.turn_data.get(_conspire_handled_key(spell_id)))


def clear_conspire_handled(state: GameState, spell_id: str) -> None:
    if not spell_id:
        return
    state.turn_data.pop(_conspire_handled_key(spell_id), None)


def _has_human_handler(state: GameState, player_id: str) -> bool:
    """Return True if the engine has a human input handler wired up.

    We treat "no handler attached" as "auto-decline" so existing tests that
    don't drive PendingChoice manually keep their pre-W29 behavior.
    """
    game = getattr(state, '_game', None)
    if game is None:
        return False
    psys = getattr(game, 'priority_system', None)
    if psys is None:
        return False
    return getattr(psys, 'get_human_action', None) is not None


def open_conspire_prompt(
    *,
    state: GameState,
    spell_obj: GameObject,
    spell_stack_item_id: str,
    caster: str,
    grant: ConspireGrant,
) -> Optional[PendingChoice]:
    """Open a conspire PendingChoice for the caster.

    Returns the installed PendingChoice (so callers can introspect / drive
    it), or ``None`` when:
      * the caster has no two color-sharing untapped creatures and so can't
        pay the conspire cost, OR
      * we auto-decline (no human handler attached, fall back to
        "auto-decline" so existing tests don't break).

    The PendingChoice's ``options`` is the list of legal creature ids the
    caster might tap. The ``min_choices`` / ``max_choices`` are both 0 for
    the decline case (an empty selection = decline) and 2 for the accept
    case. We model both branches with a single choice: the player submits
    ``[]`` to decline or ``[id_a, id_b]`` to accept.
    """
    spell_colors = set(spell_obj.characteristics.colors or set())
    legal = find_color_share_creatures(state, caster, spell_colors)

    # Need at least two color-sharing untapped creatures to be able to
    # accept the conspire cost. If we can't accept, no prompt is opened.
    if len(legal) < 2:
        return None

    # Auto-decline path: when running headless / under pure AI / under
    # tests without a human handler attached, default to "decline" so
    # legacy callers don't get stuck behind a prompt they don't know
    # about. Tests opt into the prompt by attaching a synthetic
    # ``priority_system.get_human_action`` callback or by submitting the
    # choice manually via ``game.submit_choice``.
    if not _has_human_handler(state, caster):
        return None

    options = [
        {
            "id": c.id,
            "name": c.name,
            "colors": [
                col.value if hasattr(col, 'value') else str(col)
                for col in (c.characteristics.colors or set())
            ],
        }
        for c in legal
    ]

    spell_color_strs = [
        col.value if hasattr(col, 'value') else str(col)
        for col in spell_colors
    ]

    def handler(choice: PendingChoice, selected: list, state2: GameState) -> list[Event]:
        # Empty selection = decline.
        if not selected:
            mark_conspire_handled(state2, spell_obj.id)
            return []

        # Normalise the selected ids: caller can submit either a list of
        # ids or a list of {"id": ...} dicts.
        ids: list[str] = []
        for sel in selected:
            if isinstance(sel, dict):
                tid = sel.get("id") or sel.get("value") or sel.get("target")
                if tid is not None:
                    ids.append(str(tid))
            elif sel is not None:
                ids.append(str(sel))

        # Validate: exactly two, distinct, both untapped, both controlled
        # by caster, both share a color with the spell.
        if len(ids) != 2 or ids[0] == ids[1]:
            return []

        chosen_objs: list[GameObject] = []
        for cid in ids:
            obj = state2.objects.get(cid)
            if obj is None:
                return []
            if obj.controller != caster:
                return []
            if obj.zone != ZoneType.BATTLEFIELD:
                return []
            if CardType.CREATURE not in obj.characteristics.types:
                return []
            if obj.state.tapped:
                return []
            creature_colors = set(obj.characteristics.colors or set())
            if grant.color_share_required and not (creature_colors & spell_colors):
                return []
            chosen_objs.append(obj)

        # Tap the two creatures and emit COPY_STACK_ITEM.
        # We DO NOT fire TAP events through the pipeline here; we mutate
        # state directly because the cast pipeline has already returned
        # (mid-CAST emission) and the caller emits the choice's result
        # events through state.emit. Direct tap mirrors the engine's
        # convention for "as a cost" tap (see equip cost handlers).
        events: list[Event] = []
        for c in chosen_objs:
            c.state.tapped = True
            events.append(Event(
                type=EventType.TAP,
                payload={'object_id': c.id, 'cost_payment': True},
                source=spell_obj.id,
                controller=caster,
            ))

        # Emit a CONSPIRE_TRIGGERED marker for telemetry / UI.
        events.append(Event(
            type=EventType.CONSPIRE_TRIGGERED,
            payload={
                'spell_id': spell_obj.id,
                'stack_item_id': spell_stack_item_id,
                'controller': caster,
                'tapped': [c.id for c in chosen_objs],
                'source_id': grant.source_id,
            },
            source=grant.source_id,
            controller=caster,
        ))

        # Queue the COPY_STACK_ITEM event. Per CR 702.78 you may choose
        # new targets for the copy; we plumb new_targets=None here, which
        # means the copy keeps the original's targets. UIs that want to
        # let the player retarget can chain a target_with_callback after
        # this (same pattern as Virtue of Knowledge's adventure).
        events.append(Event(
            type=EventType.COPY_STACK_ITEM,
            payload={
                'stack_item_id': spell_stack_item_id,
                # new_targets omitted: keep original targets by default.
            },
            source=grant.source_id,
            controller=caster,
        ))

        mark_conspire_handled(state2, spell_obj.id)
        return events

    prompt = (
        f"Conspire {spell_obj.name}: tap two untapped creatures sharing a color "
        f"with it (or submit empty to decline)."
    )

    choice = PendingChoice(
        choice_type="conspire",
        player=caster,
        prompt=prompt,
        options=options,
        source_id=spell_obj.id,
        # 0 = decline (empty submit), 2 = accept. We allow [0, 2] so
        # validate_selection accepts both branches.
        min_choices=0,
        max_choices=2,
        callback_data={
            "handler": handler,
            "conspire": True,
            "spell_id": spell_obj.id,
            "stack_item_id": spell_stack_item_id,
            "grant_source_id": grant.source_id,
            "spell_colors": spell_color_strs,
        },
    )
    state.pending_choice = choice
    return choice


# =============================================================================
# Module exports
# =============================================================================

__all__ = [
    "ConspireGrant",
    "CONSPIRE_GRANTS_KEY",
    "grant_conspire",
    "list_active_grants",
    "find_conspire_grants_for_spell",
    "find_color_share_creatures",
    "open_conspire_prompt",
    "mark_conspire_handled",
    "is_conspire_handled",
    "clear_conspire_handled",
]
