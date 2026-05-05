"""
Outlaws of Thunder Junction (OTJ) — Spree cost-per-mode mechanic.

Reminder text from the cards:

    Spree (Choose one or more additional costs.)
    + {1} — <effect A>
    + {2} — <effect B>
    + {3}{W} — <effect C>

Each chosen mode contributes BOTH its mana surcharge (paid up-front, at cast)
AND its effect (resolved when the spell resolves). The player must choose
at least one mode (Spree spells with no mode chosen can't be cast).

Implementation overview
-----------------------

Spree differs from FIN's Tiered in two important ways:

1. The per-mode cost MUST be paid as part of the spell's cast (R 601.2f),
   so we can't approximate it by paying at resolve time. We hook into the
   priority layer's ``_handle_cast_spell`` BEFORE the standard mana cost is
   paid, prompt the caster for a mode selection, and roll the chosen mode
   costs into the total cost.
2. The minimum is one (not zero) — a Spree spell with zero modes selected
   is illegal to cast.

Flow
----

1. Card definition stashes its modes via ``card_def._spree_modes`` (list of
   ``SpreeMode``) plus a marker ``card_def._spree = True``. We do this through
   ``make_spree_setup`` which the card's ``setup_interceptors`` returns.
2. ``_handle_cast_spell`` checks ``getattr(card.card_def, '_spree', False)``.
   If True and no mode choice has been recorded yet, it opens a
   ``PendingChoice`` that lists the modes the caster can afford. The
   caller's CAST_SPELL action returns ``[]`` while the prompt is open.
3. When the player submits, we record the chosen indices on
   ``state.turn_data[_spree_data_key(card.id)]`` and re-invoke
   ``_handle_cast_spell_sync`` so it can re-enter from the top.
4. Second pass: the cost handler reads the chosen modes and adds their
   per-mode surcharges to the cost. The standard payment + targeting flow
   then runs normally.
5. The spell's ``resolve`` callable reads the chosen-modes stash and emits
   each chosen mode's effect events in declaration order.

Notes
-----

- We use a dedicated key on ``state.turn_data`` (``"spree_choice:<card_id>"``)
  for the chosen-modes list. The per-spell scoping means flashback / re-cast
  from exile gets a fresh prompt.
- Affordability is computed by adding the printed cost + each mode's cost
  and asking the mana system whether the combined total is payable. Modes
  that are individually unaffordable are filtered out of the prompt.
- ``SpreeMode.targets_required`` is a v1 hook for "Mode N needs a target";
  the wiring side-steps in-cast targeting today (per-mode targets are taken
  at resolve via ``create_target_choice``), so this field is currently a
  metadata-only descriptor used by the UI/AI.

Public API
----------

- ``SpreeMode`` — dataclass: name, extra_cost, effect_fn, description,
  targets_required, target_kind.
- ``make_spree_setup(obj, *, base_modes, min_modes=1, max_modes=None)`` —
  attaches the spree metadata so the priority layer can detect it. Returns
  an empty interceptor list (no per-event hooks needed; the priority layer
  drives the prompt directly).
- ``make_spree_resolve(modes)`` — builds a ``(targets, state) -> list[Event]``
  resolve callable that fires each chosen mode's effects in order.
- ``compute_affordable_spree_modes(modes, state, player_id, base_cost)`` —
  helper for tests/UI. Returns ``[(idx, mode), ...]``.
- ``get_chosen_spree_modes(state, card_id) -> list[int] | None`` — read.
- ``record_spree_choice(state, card_id, indices)`` — write.
- ``clear_spree_choice(state, card_id)`` — cleanup (call on resolve).
- ``TURN_DATA_SPREE_KEY`` — turn_data key prefix (constant).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    PendingChoice,
    new_id,
)
from .mana import ManaCost
from .casting_costs import add_mana_costs


TURN_DATA_SPREE_KEY = "spree_choice"


# =============================================================================
# Mode definition
# =============================================================================


@dataclass
class SpreeMode:
    """One mode of a Spree spell.

    Attributes:
        name: short label for UI, e.g. "Untap creatures".
        extra_cost: ``ManaCost`` or string (``"{1}"``, ``"{2}{B}"``, ...). The
            additional mana cost paid IN ADDITION to the printed cost when
            this mode is chosen. Spree per-mode costs are always non-empty
            (``"+ {0}"`` would be redundant).
        effect_fn: ``(spell_obj, state, targets) -> list[Event]`` — the events
            to emit when this mode resolves. ``targets`` is the per-stack-item
            target list passed to the resolve callable; modes that need their
            own target choice can call ``create_target_choice`` from inside
            ``effect_fn`` (most existing OTJ Spree resolves do this).
        description: long-form UI text. Defaults to ``name``.
        targets_required: number of targets this mode needs (advisory; the
            current resolve flow handles targeting per-mode via
            ``create_target_choice`` callbacks).
        target_kind: brief target descriptor (``"creature"``, ``"any"``, ...).
            Advisory metadata only.
    """

    name: str
    extra_cost: Any  # ManaCost | str
    effect_fn: Callable[[GameObject, GameState, list], list[Event]]
    description: str = ""
    targets_required: int = 0
    target_kind: str = "any"

    def resolved_extra_cost(self) -> ManaCost:
        """Parse ``extra_cost`` into a ManaCost (empty if free)."""
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
        cost = self.resolved_extra_cost()
        cost_str = cost.to_string() if not cost.is_free() else "{0}"
        body = self.description or self.name
        return f"+ {cost_str} - {body}"


# =============================================================================
# Affordability
# =============================================================================


def _can_pay(state: GameState, player_id: str, cost: ManaCost) -> bool:
    """Helper: does the player have access to enough mana to pay ``cost``?

    Uses ``ManaSystem.can_cast`` (pool + untapped lands) when available so
    affordability matches the cast pipeline. Falls back to a pool-only
    check via ``ManaPool.can_pay`` if no system is attached.
    """
    if cost.is_free():
        return True
    game = getattr(state, "_game", None)
    mana_system = getattr(game, "mana_system", None) if game else None
    if mana_system is not None:
        # Prefer can_cast (pool + auto-tap untapped lands).
        try:
            return bool(mana_system.can_cast(player_id, cost))
        except Exception:
            pass
        # Fallback: pool-only.
        try:
            pool = mana_system.get_pool(player_id)
            return bool(pool.can_pay(cost))
        except Exception:
            return False
    return False


def compute_affordable_spree_modes(
    modes: Sequence[SpreeMode],
    state: GameState,
    player_id: str,
    base_cost: ManaCost,
) -> list[tuple[int, SpreeMode]]:
    """Return modes the caster can afford as a single-mode pick.

    Each mode is checked independently against (base_cost + mode.extra_cost).
    Multi-mode combos are NOT pre-validated here — the cost-handler enforces
    full affordability when the choice is submitted.
    """
    out: list[tuple[int, SpreeMode]] = []
    for idx, mode in enumerate(modes):
        total = add_mana_costs(base_cost, mode.resolved_extra_cost())
        if _can_pay(state, player_id, total):
            out.append((idx, mode))
    return out


# =============================================================================
# Choice stash (turn_data)
# =============================================================================


def _spree_data_key(card_id: str) -> str:
    return f"{TURN_DATA_SPREE_KEY}:{card_id}"


def get_chosen_spree_modes(state: GameState, card_id: str) -> Optional[list[int]]:
    """Read the mode indices chosen for ``card_id``, or ``None`` if not chosen."""
    if not card_id:
        return None
    raw = state.turn_data.get(_spree_data_key(card_id))
    if raw is None:
        return None
    if isinstance(raw, list):
        return list(raw)
    return [int(raw)]


def record_spree_choice(state: GameState, card_id: str, indices: Sequence[int]) -> None:
    """Persist the chosen mode indices for a Spree spell."""
    if not card_id:
        return
    state.turn_data[_spree_data_key(card_id)] = [int(i) for i in indices]


def clear_spree_choice(state: GameState, card_id: str) -> None:
    """Remove the chosen-modes stash (call from resolve to keep state clean)."""
    if not card_id:
        return
    state.turn_data.pop(_spree_data_key(card_id), None)


# =============================================================================
# Selection normaliser
# =============================================================================


def _normalize_picked_indices(selected: list) -> list[int]:
    """Normalise a PendingChoice ``selected`` list to ordered int indices."""
    out: list[int] = []
    for sel in selected or []:
        idx: Optional[int] = None
        if isinstance(sel, dict):
            for key in ("index", "id", "value"):
                if key in sel:
                    try:
                        idx = int(sel[key])
                    except (TypeError, ValueError):
                        idx = None
                    break
        else:
            try:
                idx = int(sel)
            except (TypeError, ValueError):
                idx = None
        if idx is not None:
            out.append(idx)
    return out


# =============================================================================
# Setup (metadata-only) and resolve
# =============================================================================


def make_spree_setup(
    obj: GameObject,
    *,
    base_modes: Sequence[SpreeMode],
    min_modes: int = 1,
    max_modes: Optional[int] = None,
) -> list[Interceptor]:
    """Attach Spree metadata to the card definition so the priority layer
    can detect and prompt for mode selection at cast time.

    The metadata ride on ``card_def`` (not the in-flight GameObject) so that
    casts of fresh copies of the same card pick it up automatically.

    Args:
        obj: GameObject for the spell (used to access ``obj.card_def``).
        base_modes: ordered list of ``SpreeMode``. Order matches the printed
            ``+ <cost> — <effect>`` order; resolution fires effects in this
            order (regardless of submission order).
        min_modes: minimum modes that must be chosen. Spree printed text
            requires at least one (default).
        max_modes: maximum modes that may be chosen. Defaults to
            ``len(base_modes)`` (Spree allows "one or more").

    Returns an empty interceptor list — Spree integration is driven from
    ``priority._handle_cast_spell``, not from event interceptors.
    """
    card_def = getattr(obj, "card_def", None)
    if card_def is None:
        return []

    cap_min = max(1, int(min_modes))  # Spree always requires at least one
    cap_max = int(max_modes) if max_modes is not None else len(base_modes)
    if cap_max < cap_min:
        cap_max = cap_min

    # Stash on the CardDefinition so priority can look it up directly. We
    # use sentinel attributes (underscore-prefixed) so they don't collide
    # with the dataclass schema.
    card_def._spree = True  # type: ignore[attr-defined]
    card_def._spree_modes = list(base_modes)  # type: ignore[attr-defined]
    card_def._spree_min_modes = cap_min  # type: ignore[attr-defined]
    card_def._spree_max_modes = cap_max  # type: ignore[attr-defined]

    return []


def make_spree_resolve(modes: Sequence[SpreeMode]):
    """Build a resolve callable that fires each chosen mode's effects in
    declaration order. Compatible with the standard
    ``(targets, state) -> list[Event]`` resolve signature.

    Edge cases:
    - If no choice was recorded (e.g., the spell was force-cast outside of
      the priority handler), we fall back to firing the lowest-cost mode so
      the spell does *something*.
    - Out-of-range indices are silently skipped.
    - The chosen-modes stash is cleared after resolve so flashback / replay
      starts fresh.
    """
    mode_list = list(modes)

    def _resolve(targets, state: GameState) -> list[Event]:
        spell_obj: Optional[GameObject] = None
        chosen: Optional[list[int]] = None

        # Locate the spell whose card_def.resolve is us. Prefer the one with
        # a recorded choice; fall back to any matching spell.
        for key, val in list(state.turn_data.items()):
            if not key.startswith(TURN_DATA_SPREE_KEY + ":"):
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
            # No stash; try to find any matching spell on the stack/state.
            spell_obj = next(
                (
                    o
                    for o in state.objects.values()
                    if getattr(getattr(o, "card_def", None), "resolve", None) is _resolve
                ),
                None,
            )
            if spell_obj is None:
                return []

        if not chosen:
            # No recorded choice (shouldn't happen via normal cast path).
            # Fall back to the cheapest mode so resolution isn't a complete no-op.
            if mode_list:
                cheap_idx = min(
                    range(len(mode_list)),
                    key=lambda i: mode_list[i].resolved_extra_cost().mana_value,
                )
                chosen = [cheap_idx]
            else:
                return []

        events: list[Event] = []
        for idx in chosen:
            if idx < 0 or idx >= len(mode_list):
                continue
            mode = mode_list[idx]
            try:
                produced = mode.effect_fn(spell_obj, state, targets) or []
            except TypeError:
                # Backward-compat: some legacy effect_fns may use (obj, state)
                try:
                    produced = mode.effect_fn(spell_obj, state) or []  # type: ignore[arg-type]
                except Exception:
                    produced = []
            except Exception:
                produced = []
            events.extend(produced)

        clear_spree_choice(state, spell_obj.id)
        return events

    return _resolve


# =============================================================================
# Choice handler used by priority._handle_cast_spell
# =============================================================================


def open_spree_choice(
    *,
    obj: GameObject,
    state: GameState,
    caster: str,
    base_cost: ManaCost,
    modes: Sequence[SpreeMode],
    min_modes: int,
    max_modes: int,
    on_complete: Callable[[list[int], GameState], list[Event]],
) -> list[Event]:
    """Compute the affordable mode list and install a PendingChoice.

    On submission, the choice handler:
      1. Validates min/max counts.
      2. Records the selection via ``record_spree_choice``.
      3. Calls ``on_complete(indices, state)`` (priority layer's continuation).

    Returns a list of telemetry events (currently a single
    ``SPREE_MODE_CHOSEN`` marker once the prompt opens).
    """
    affordable = compute_affordable_spree_modes(modes, state, caster, base_cost)
    if not affordable:
        # Caster can't afford any single mode -> spell is uncastable. Surface
        # this by returning an empty list; the priority handler treats the
        # original CAST_SPELL action as illegal.
        return []

    options = [
        {"index": idx, "text": mode.label(), "mode_cost": mode.resolved_extra_cost().to_string()}
        for idx, mode in affordable
    ]

    capped_max = min(max_modes, len(affordable))
    capped_min = min(min_modes, capped_max)

    def handler(choice: PendingChoice, selected: list, state2: GameState) -> list[Event]:
        picked = _normalize_picked_indices(selected)
        # Restrict to indices that were actually offered.
        offered = {idx for idx, _ in affordable}
        chosen = [p for p in picked if p in offered]
        if len(chosen) < capped_min:
            return []
        chosen = chosen[:capped_max]
        record_spree_choice(state2, obj.id, chosen)
        return list(on_complete(chosen, state2) or [])

    prompt = f"Spree: choose one or more additional costs for {obj.name}"
    choice = PendingChoice(
        choice_type="spree",
        player=caster,
        prompt=prompt,
        options=options,
        source_id=obj.id,
        min_choices=capped_min,
        max_choices=capped_max,
        callback_data={
            "handler": handler,
            "spree": True,
            "card_id": obj.id,
        },
    )
    state.pending_choice = choice

    return [
        Event(
            type=EventType.SPREE_MODE_CHOSEN,
            payload={
                "card_id": obj.id,
                "controller": caster,
                "modes": [
                    {
                        "name": mode.name,
                        "extra_cost": mode.resolved_extra_cost().to_string(),
                        "description": mode.description or mode.name,
                    }
                    for _, mode in affordable
                ],
                "selected": None,  # filled in by handler
            },
            source=obj.id,
            controller=caster,
        )
    ]


def total_spree_extra_cost(modes: Sequence[SpreeMode], indices: Sequence[int]) -> ManaCost:
    """Sum the per-mode extra costs for the chosen indices."""
    total = ManaCost()
    for i in indices:
        if 0 <= i < len(modes):
            total = add_mana_costs(total, modes[i].resolved_extra_cost())
    return total


def is_spree_card(card_or_def: Any) -> bool:
    """Return True if ``card_or_def`` is a Spree spell.

    Accepts either a ``GameObject`` (we look at ``.card_def``) or a
    ``CardDefinition`` directly.
    """
    cdef = getattr(card_or_def, "card_def", card_or_def)
    return bool(getattr(cdef, "_spree", False))


def get_spree_modes(card_or_def: Any) -> list[SpreeMode]:
    """Return the configured ``SpreeMode`` list for a Spree card (else [])."""
    cdef = getattr(card_or_def, "card_def", card_or_def)
    return list(getattr(cdef, "_spree_modes", []) or [])


def get_spree_minmax(card_or_def: Any) -> tuple[int, int]:
    """Return ``(min_modes, max_modes)`` for a Spree card."""
    cdef = getattr(card_or_def, "card_def", card_or_def)
    modes = get_spree_modes(cdef)
    cap_max = int(getattr(cdef, "_spree_max_modes", len(modes)) or len(modes))
    cap_min = int(getattr(cdef, "_spree_min_modes", 1) or 1)
    return cap_min, cap_max
