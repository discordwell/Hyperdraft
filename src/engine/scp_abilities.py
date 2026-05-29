"""SCP-native activated / modal ability descriptors + factory.

SCP cards declare activated abilities through ``make_scp_activated_ability``,
which registers an ``SCPActivatedAbility`` onto ``obj.state.activated_abilities``
(the same list the engine already uses; the list is heterogeneous because MTG
``ActivatedAbility`` objects also live there — every SCP reader type-guards via
``is_scp_ability``). We do NOT subclass the mana-centric MTG ``ActivatedAbility``:
its cost grammar can't express ethics/secrecy/briefing, and forcing SCP through
it (empty ``cost_text`` + all logic in ``effect_fn``, as Mnestic Wake does) is
the anti-pattern this module replaces.

Dispatch lives in ``scp.activate_ability``; legal-action surfacing in
``scp_legal_actions``; AI valuation in ``scp_adapter``. This module is pure data
+ registration so it imports nothing from ``scp`` (no cycle).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.engine.scp_costs import SCPCost, SCPValueHint, describe_scp_cost


# A single mode of a "choose one" ability. ``effect_fn`` is the SCP-native
# 2-arg signature ``(obj, state) -> list[Event]``.
@dataclass
class SCPMode:
    label: str
    effect_fn: Callable[[Any, Any], list]
    tags: tuple[str, ...] = ()
    value_hint: Optional[SCPValueHint] = None


@dataclass
class SCPActivatedAbility:
    cost: SCPCost
    description: str
    effect_fn: Optional[Callable[[Any, Any], list]] = None  # None for modal
    modes: Optional[list[SCPMode]] = None
    once_per_turn: bool = False
    once_per_game: bool = False
    precondition_fn: Optional[Callable[[Any, Any], bool]] = None
    value_hint: Optional[SCPValueHint] = None
    # Marker so heterogeneous-list readers can identify SCP abilities cheaply.
    is_scp: bool = True
    # Assigned at registration; runtime gating state.
    ability_index: int = 0
    activations_this_turn: int = 0
    used_this_game: bool = False

    @property
    def is_modal(self) -> bool:
        return bool(self.modes)

    def reset_turn(self) -> None:
        self.activations_this_turn = 0


def is_scp_ability(ability: Any) -> bool:
    return isinstance(ability, SCPActivatedAbility) or bool(getattr(ability, "is_scp", False))


def _primary_code(ability: SCPActivatedAbility):
    """Identity key for dedup: the compiled code of the primary callable.

    ``def`` statements compile once at module load, so two runs of the same
    setup function share a ``__code__`` object (``is``-equal) while genuinely
    distinct abilities do not. Mirrors ``activated.register_activated_ability``.
    """
    fn = ability.effect_fn
    if fn is None and ability.modes:
        fn = ability.modes[0].effect_fn
    return getattr(fn, "__code__", None)


def make_scp_activated_ability(
    obj,
    *,
    cost: SCPCost,
    description: str,
    effect_fn: Optional[Callable[[Any, Any], list]] = None,
    modes: Optional[list[SCPMode]] = None,
    once_per_turn: bool = False,
    once_per_game: bool = False,
    precondition_fn: Optional[Callable[[Any, Any], bool]] = None,
    value_hint: Optional[SCPValueHint] = None,
) -> SCPActivatedAbility:
    """Register an SCP activated (or modal) ability on ``obj``.

    Call from a card's ``setup_interceptors`` (return ``[]`` or include the
    ability — the registration is the side effect). Exactly one of ``effect_fn``
    / ``modes`` must be supplied. De-duplicates against re-runs of the same
    setup (setup_interceptors runs on both HAND init and BATTLEFIELD entry).
    """
    if (effect_fn is None) == (modes is None):
        raise ValueError("make_scp_activated_ability: supply exactly one of effect_fn or modes")

    ability = SCPActivatedAbility(
        cost=cost,
        description=description,
        effect_fn=effect_fn,
        modes=modes,
        once_per_turn=once_per_turn,
        once_per_game=once_per_game,
        precondition_fn=precondition_fn,
        value_hint=value_hint,
    )

    if not isinstance(getattr(obj.state, "activated_abilities", None), list):
        obj.state.activated_abilities = []

    new_code = _primary_code(ability)
    for existing in obj.state.activated_abilities:
        if not is_scp_ability(existing):
            continue
        if existing.description != description:
            continue
        existing_code = _primary_code(existing)
        if new_code is not None and existing_code is not None and new_code is existing_code:
            return existing  # same setup re-run — already registered

    ability.ability_index = len(obj.state.activated_abilities)
    obj.state.activated_abilities.append(ability)
    return ability


def serialize_scp_abilities(obj, state) -> list[dict]:
    """Client-facing view of an object's SCP activated/modal abilities, for the
    board's Activate affordance. ``affordable``/``spent`` are from the
    controller's viewpoint."""
    from src.engine.scp_costs import can_pay_scp_cost, describe_scp_cost

    out: list[dict] = []
    for idx, ability in enumerate(getattr(obj.state, "activated_abilities", None) or []):
        if not is_scp_ability(ability):
            continue
        try:
            affordable, _ = can_pay_scp_cost(obj, state, ability.cost)
        except NotImplementedError:
            affordable = False
        spent = (
            (ability.once_per_game and ability.used_this_game)
            or (ability.once_per_turn and ability.activations_this_turn > 0)
        )
        entry: dict = {
            "index": idx,
            "description": ability.description,
            "cost": describe_scp_cost(ability.cost),
            "is_modal": ability.is_modal,
            "affordable": bool(affordable),
            "spent": bool(spent),
        }
        if ability.is_modal:
            entry["modes"] = [{"index": i, "label": m.label} for i, m in enumerate(ability.modes)]
        out.append(entry)
    return out


__all__ = [
    "SCPMode",
    "SCPActivatedAbility",
    "is_scp_ability",
    "make_scp_activated_ability",
    "serialize_scp_abilities",
]
