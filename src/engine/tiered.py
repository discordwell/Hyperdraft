"""
Final Fantasy (FIN) — Tiered cost mechanic.

Reminder text from the cards:

    Tiered (Choose one additional cost.)
    * Cure   - {0}     - <effect>
    * Cura   - {1}     - <effect, slightly stronger>
    * Curaga - {3}{W}  - <effect, even stronger>

The mechanic prompts the casting player to choose exactly one tier as the spell
is cast. The chosen tier's mana surcharge is paid AT cast time (we deduct it
from the player's mana pool right after the printed cost has been paid),
and the chosen tier's effect_fn fires when the spell resolves.

Implementation notes
--------------------

We can't (and don't want to) modify ``src/engine/priority.py`` from this card,
so the integration point is the ``CAST`` event. By the time we observe ``CAST``,
the printed mana cost has already been paid by the priority handler. We then:

1. Filter the configured tiers down to the ones the caster can still afford
   (using the manager's ``can_pay`` against the current pool plus available
   untapped lands).
2. Open a ``modal``-style ``PendingChoice`` listing the affordable tiers.
3. When the player submits, deduct the chosen tier's extra cost via
   ``mana_system.pay_cost`` (which auto-taps lands as needed) and stash the
   chosen tier index on ``state.turn_data`` keyed by the spell's id.
4. The card definition's ``resolve`` callable reads that stash and returns
   the chosen tier's effect events.

The choice handler is installed on a fresh ``PendingChoice`` so the existing
``submit_choice`` flow in ``game.py`` (line ~1403) drives the resolution; this
is the same pattern used by additional-cost OR steps in ``priority.py``.

Public API
----------

- ``TierDefinition`` — dataclass describing one tier (name, extra_cost, effect_fn).
- ``make_tiered_setup(obj, *, tiers)`` — returns interceptors to wire on the
  card. Pair this with ``make_tiered_resolve(tiers)`` set as the card's
  ``resolve=`` callable.
- ``make_tiered_resolve(tiers)`` — builds the resolve_fn that dispatches
  effects for the chosen tier.
- ``compute_affordable_tiers`` — exported for testing.
- ``TURN_DATA_TIER_KEY`` — turn_data key prefix used to stash a spell's choice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    PendingChoice,
    new_id,
)
from .mana import ManaCost


TURN_DATA_TIER_KEY = "tiered_choice"


# =============================================================================
# Tier definition
# =============================================================================


@dataclass
class TierDefinition:
    """One tier of a Tiered spell.

    Attributes:
        name: human-readable label, e.g. "Cure", "Cura", "Curaga".
        extra_cost: a ``ManaCost`` or its string form (e.g. ``"{1}"``,
            ``"{3}{W}"``). ``""``/``"{0}"`` means no extra mana.
        effect_fn: ``(obj, state) -> list[Event]`` — the events to emit when
            this tier resolves. ``obj`` is the spell's GameObject; the caster
            can be read off ``obj.controller``.
        description: optional UI string. Defaults to ``name``.
    """
    name: str
    extra_cost: Any  # ManaCost | str
    effect_fn: Callable[[GameObject, GameState], list[Event]]
    description: str = ""

    def resolved_extra_cost(self) -> ManaCost:
        """Return ``extra_cost`` parsed into a ManaCost (empty for free tiers)."""
        cost = self.extra_cost
        if cost is None:
            return ManaCost()
        if isinstance(cost, ManaCost):
            return cost
        s = str(cost).strip()
        if not s or s == "{0}":
            return ManaCost()
        return ManaCost.parse(s)

    def label(self) -> str:
        """Pretty label for the modal choice (e.g. ``"Cura - {1}"``)."""
        cost = self.resolved_extra_cost()
        cost_str = cost.to_string() if not cost.is_free() else "{0}"
        if self.description:
            return f"{self.name} - {cost_str} - {self.description}"
        return f"{self.name} - {cost_str}"


# =============================================================================
# Affordability
# =============================================================================


def compute_affordable_tiers(
    tiers: Sequence[TierDefinition],
    state: GameState,
    player_id: str,
) -> list[tuple[int, TierDefinition]]:
    """Return ``[(index, tier), ...]`` for tiers the player can pay for.

    A free tier (extra_cost ``{0}``/empty) is always affordable. For tiers
    with a non-empty cost we ask the mana system whether the player could
    pay the extra cost using their current pool plus any auto-tappable lands.
    If no mana system is attached (test harnesses) we fall back to the pool's
    own ``can_pay`` check.
    """
    out: list[tuple[int, TierDefinition]] = []
    game = getattr(state, "_game", None)
    mana_system = getattr(game, "mana_system", None) if game else None
    pool = None
    if mana_system is not None:
        try:
            pool = mana_system.get_pool(player_id)
        except Exception:
            pool = None

    for idx, tier in enumerate(tiers):
        cost = tier.resolved_extra_cost()
        if cost.is_free():
            out.append((idx, tier))
            continue
        affordable = False
        if mana_system is not None:
            try:
                if mana_system.can_pay(player_id, cost):
                    affordable = True
            except Exception:
                affordable = False
        if not affordable and pool is not None:
            try:
                affordable = pool.can_pay(cost)
            except Exception:
                affordable = False
        if affordable:
            out.append((idx, tier))
    return out


# =============================================================================
# Choice handling
# =============================================================================


def _tier_data_key(card_id: str) -> str:
    return f"{TURN_DATA_TIER_KEY}:{card_id}"


def get_chosen_tier_indices(state: GameState, card_id: str) -> Optional[list[int]]:
    """Read the tier indices a player chose for a spell, if any.

    Returns a list of tier indices (in chosen order) or ``None`` if no choice
    has been recorded. Callers that only care about the first/only tier can
    use ``get_chosen_tier_index``.
    """
    if not card_id:
        return None
    raw = state.turn_data.get(_tier_data_key(card_id))
    if raw is None:
        return None
    if isinstance(raw, list):
        return list(raw)
    return [int(raw)]


def get_chosen_tier_index(state: GameState, card_id: str) -> Optional[int]:
    """Read the (first) tier index a player chose for a spell, if any."""
    indices = get_chosen_tier_indices(state, card_id)
    if not indices:
        return None
    return indices[0]


def clear_chosen_tier(state: GameState, card_id: str) -> None:
    """Remove the stash entry for ``card_id``."""
    if not card_id:
        return
    state.turn_data.pop(_tier_data_key(card_id), None)


def _record_tier_choice(state: GameState, card_id: str, tier_indices) -> None:
    if isinstance(tier_indices, int):
        state.turn_data[_tier_data_key(card_id)] = [tier_indices]
    else:
        state.turn_data[_tier_data_key(card_id)] = list(tier_indices)


def _normalize_picked_indices(selected: list) -> list[int]:
    """Normalize PendingChoice selection (list of dicts/ints) to int indices."""
    out: list[int] = []
    for sel in selected or []:
        idx: Optional[int] = None
        if isinstance(sel, dict):
            if "index" in sel:
                try:
                    idx = int(sel["index"])
                except (TypeError, ValueError):
                    idx = None
            elif "id" in sel:
                try:
                    idx = int(sel["id"])
                except (TypeError, ValueError):
                    idx = None
        else:
            try:
                idx = int(sel)
            except (TypeError, ValueError):
                idx = None
        if idx is not None:
            out.append(idx)
    return out


def _make_choice_handler(
    tiers: Sequence[TierDefinition],
    affordable: Sequence[tuple[int, TierDefinition]],
    card_id: str,
    player_id: str,
):
    """Build the PendingChoice handler that records the tier(s) and pays cost."""
    affordable_by_idx = {idx: tier for idx, tier in affordable}

    def handler(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
        picked = _normalize_picked_indices(selected)
        # Filter to only valid affordable picks, preserving order.
        chosen: list[tuple[int, TierDefinition]] = []
        for p in picked:
            if p in affordable_by_idx:
                chosen.append((p, affordable_by_idx[p]))
        if not chosen:
            return []

        # Pay the combined extra cost. We pay each tier's cost in turn so the
        # mana system can auto-tap incrementally; if any payment fails, abort
        # without recording a choice.
        game = getattr(state, "_game", None)
        mana_system = getattr(game, "mana_system", None) if game else None
        for idx, tier in chosen:
            cost = tier.resolved_extra_cost()
            if cost.is_free():
                continue
            if mana_system is None:
                return []
            try:
                paid = mana_system.pay_cost(player_id, cost)
            except Exception:
                paid = False
            if not paid:
                return []

        _record_tier_choice(state, card_id, [idx for idx, _ in chosen])
        return []

    return handler


# =============================================================================
# Setup (interceptor) and resolve helpers
# =============================================================================


def _tiers_payload(tiers: Sequence[TierDefinition]) -> list[dict]:
    """Build the EventType.TIERED_CHOICE 'tiers' payload list."""
    return [
        {
            "name": tier.name,
            "extra_cost": tier.resolved_extra_cost().to_string(),
            "effect_label": tier.description or tier.name,
        }
        for tier in tiers
    ]


def _open_tiered_choice(
    *,
    obj: GameObject,
    state: GameState,
    tiers: Sequence[TierDefinition],
    caster: str,
    min_choices: int,
    max_choices: int,
) -> list[Event]:
    """Compute affordable tiers and install a PendingChoice."""
    affordable = compute_affordable_tiers(tiers, state, caster)
    if not affordable:
        # No tiers are payable. Honor min_choices=0 by recording an empty
        # selection; otherwise the spell resolves with no tier effect.
        if min_choices == 0:
            _record_tier_choice(state, obj.id, [])
        return [
            Event(
                type=EventType.TIERED_CHOICE,
                payload={
                    "player": caster,
                    "card_id": obj.id,
                    "tiers": _tiers_payload(tiers),
                    "selected": [],
                },
                source=obj.id,
                controller=caster,
            )
        ]

    if state.pending_choice is not None:
        # Another choice is already pending; we can't stack two simultaneously.
        # Default to the cheapest free tier (or first affordable) so the
        # spell doesn't silently fizzle.
        _record_tier_choice(state, obj.id, [affordable[0][0]])
        return []

    # Auto-resolve when only one tier is legal AND we're picking exactly one.
    if len(affordable) == 1 and max_choices == 1 and min_choices >= 1:
        idx, tier = affordable[0]
        cost = tier.resolved_extra_cost()
        if not cost.is_free():
            game = getattr(state, "_game", None)
            mana_system = getattr(game, "mana_system", None) if game else None
            if mana_system is not None:
                try:
                    mana_system.pay_cost(caster, cost)
                except Exception:
                    pass
        _record_tier_choice(state, obj.id, [idx])
        return [
            Event(
                type=EventType.TIERED_CHOICE,
                payload={
                    "player": caster,
                    "card_id": obj.id,
                    "tiers": _tiers_payload(tiers),
                    "selected": [idx],
                },
                source=obj.id,
                controller=caster,
            )
        ]

    options = [
        {"index": idx, "text": tier.label()}
        for idx, tier in affordable
    ]
    prompt = f"Choose a tier for {obj.name}"
    capped_max = min(max_choices, len(affordable))
    capped_min = min(min_choices, capped_max)
    choice = PendingChoice(
        choice_type="modal",
        player=caster,
        prompt=prompt,
        options=options,
        source_id=obj.id,
        min_choices=capped_min,
        max_choices=capped_max,
        callback_data={
            "handler": _make_choice_handler(tiers, affordable, obj.id, caster),
            "tiered": True,
        },
    )
    state.pending_choice = choice

    return [
        Event(
            type=EventType.TIERED_CHOICE,
            payload={
                "player": caster,
                "card_id": obj.id,
                "tiers": _tiers_payload(tiers),
            },
            source=obj.id,
            controller=caster,
        )
    ]


def make_tiered_setup(
    obj: GameObject,
    *,
    tiers: Sequence[TierDefinition],
    min_choices: int = 1,
    max_choices: int = 1,
) -> list[Interceptor]:
    """Build the interceptor list that drives the tiered cost prompt.

    Wire this on the card's ``setup_interceptors``. Pair it with
    ``make_tiered_resolve(tiers)`` set as the card's ``resolve=`` so the
    chosen tier's effect_fn actually fires.

    Args:
        obj: the GameObject for the spell being cast.
        tiers: the tier menu, in cheapest-to-most-expensive order.
        min_choices: minimum number of tiers the player must select. ``1``
            (default) matches FIN's "Choose one additional cost"; pass ``0``
            to allow opting out of all tiers.
        max_choices: maximum number of tiers selectable. ``1`` (default)
            matches FIN's "Choose one"; pass ``len(tiers)`` to model
            "choose one or more" cards.

    The interceptor:
      * Filters to ``CAST``/``SPELL_CAST`` events whose ``card_id``/``spell_id``
        matches ``obj.id``.
      * Reacts by computing affordable tiers and opening a PendingChoice.
      * Records the selection on ``state.turn_data`` for resolve to read.

    Tiers with no remaining choice (only one affordable) auto-resolve without
    a prompt. If no tier is affordable, the spell simply runs with no tier
    effect (its base printed cost was already paid by the priority handler).
    """
    obj_id = obj.id
    tier_list = list(tiers)
    cap_min = max(0, int(min_choices))
    cap_max = max(cap_min, int(max_choices))

    def filt(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.CAST, EventType.SPELL_CAST):
            return False
        spell_id = event.payload.get("spell_id") or event.payload.get("card_id")
        if spell_id != obj_id:
            return False
        # Avoid re-prompting if a tier is already recorded for this spell
        # (e.g., pipeline replays the CAST event).
        if get_chosen_tier_indices(state, obj_id) is not None:
            return False
        return True

    def handler(event: Event, state: GameState) -> InterceptorResult:
        caster = (
            event.payload.get("caster")
            or event.payload.get("controller")
            or event.controller
            or obj.controller
        )
        new_events = _open_tiered_choice(
            obj=obj,
            state=state,
            tiers=tier_list,
            caster=caster,
            min_choices=cap_min,
            max_choices=cap_max,
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    return [
        Interceptor(
            id=new_id(),
            source=obj_id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=filt,
            handler=handler,
            duration="forever",
        )
    ]


def make_tiered_resolve(tiers: Sequence[TierDefinition]):
    """Build a resolve_fn that emits the chosen tier(s) events.

    Returns a function with the targets-style signature
    ``(targets, state) -> list[Event]`` — the same shape used elsewhere in
    ``src/engine/spell_resolve.py``. When multiple tiers were selected,
    their effect events are emitted in selection order.

    If no tier was chosen (e.g., insufficient mana for any tier), we fall
    back to the lowest free tier when one exists; otherwise the spell
    resolves without effect.
    """
    tier_list = list(tiers)

    def _resolve(targets, state: GameState) -> list[Event]:
        # ``targets`` is unused for tier dispatch — the chosen tier's
        # ``effect_fn`` is responsible for any further targeting. We locate
        # the resolving spell by checking which GameObject's card_def has
        # ``_resolve`` as its resolve callable.
        spell_obj: Optional[GameObject] = None
        chosen: Optional[list[int]] = None

        for key, val in list(state.turn_data.items()):
            if not key.startswith(TURN_DATA_TIER_KEY + ":"):
                continue
            card_id = key.split(":", 1)[1]
            obj = state.objects.get(card_id)
            if obj is None:
                continue
            cdef = getattr(obj, "card_def", None)
            if cdef is None:
                continue
            if getattr(cdef, "resolve", None) is _resolve:
                spell_obj = obj
                if isinstance(val, list):
                    chosen = list(val)
                elif val is None:
                    chosen = None
                else:
                    chosen = [int(val)]
                break

        if spell_obj is None:
            # Resolve called outside our normal flow (e.g., orphan stack
            # item). Try to find any GameObject pointing at us.
            spell_obj = next(
                (o for o in state.objects.values()
                 if getattr(getattr(o, "card_def", None), "resolve", None) is _resolve),
                None,
            )
            if spell_obj is None:
                return []

        if not chosen:
            # No tier recorded. Fall back to the first free tier if any.
            for idx, tier in enumerate(tier_list):
                if tier.resolved_extra_cost().is_free():
                    chosen = [idx]
                    break
            if not chosen:
                return []

        events: list[Event] = []
        for idx in chosen:
            if idx < 0 or idx >= len(tier_list):
                continue
            tier = tier_list[idx]
            try:
                produced = tier.effect_fn(spell_obj, state) or []
            except Exception:
                produced = []
            events.extend(produced)

        # Clean up the stash so re-casts (e.g. flashback) get a fresh prompt.
        clear_chosen_tier(state, spell_obj.id)
        return events

    return _resolve
