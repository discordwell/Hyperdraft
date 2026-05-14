"""
Hyperdraft Targeting System

Handles target selection, validation, and legality checks.
Supports hexproof, shroud, protection, and other targeting restrictions.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Union
from enum import Enum, auto

from .types import (
    GameState, GameObject, ZoneType, CardType, Color,
    Event, EventType
)
from .queries import get_types, get_colors, has_ability


class TargetType(Enum):
    """Types of things that can be targeted."""
    PERMANENT = auto()
    CREATURE = auto()
    PLAYER = auto()
    SPELL = auto()  # On the stack
    CARD = auto()   # In graveyard, hand, etc.
    ANY = auto()    # "Any target" (creature, player, or planeswalker)


@dataclass
class TargetFilter:
    """
    Filter for determining what can be targeted.

    Examples:
        - "target creature" -> types={CardType.CREATURE}
        - "target creature you control" -> types={CardType.CREATURE}, controller='you'
        - "target red permanent" -> colors={Color.RED}
        - "target creature with flying" -> abilities=['flying']
    """
    # Type restrictions
    types: set[CardType] = None
    subtypes: set[str] = None
    supertypes: set[str] = None

    # Color restrictions
    colors: set[Color] = None
    is_colorless: bool = False

    # Controller restrictions
    controller: Literal['you', 'opponent', 'any'] = 'any'

    # Zone restrictions (default battlefield for permanents)
    zones: list[ZoneType] = field(default_factory=lambda: [ZoneType.BATTLEFIELD])

    # Ability requirements
    abilities: list[str] = None  # e.g., ['flying', 'trample']

    # Power/toughness requirements
    power_max: Optional[int] = None
    power_min: Optional[int] = None
    toughness_max: Optional[int] = None
    toughness_min: Optional[int] = None

    # Mana value requirements
    mana_value_max: Optional[int] = None
    mana_value_min: Optional[int] = None

    # State requirements
    tapped: Optional[bool] = None
    untapped: Optional[bool] = None
    attacking: Optional[bool] = None
    blocking: Optional[bool] = None

    # Exclusions
    exclude_self: bool = False  # "another target creature"
    exclude_ids: set[str] = field(default_factory=set)

    # "Any target" semantics: explicitly include players even when ``types``
    # restricts object matching to creature/planeswalker. Without this flag,
    # ``TargetingSystem._can_target_players`` only allows players when
    # ``types is None`` (used by ``target_player``), which incorrectly
    # excluded players from "any target" filters before Phase 5b's
    # engine-emitted PendingChoice exposed the gap.
    includes_players: bool = False

    # Custom filter function
    custom_filter: Callable[[GameObject, GameState], bool] = None

    def matches(
        self,
        obj: GameObject,
        state: GameState,
        source: Optional[GameObject] = None
    ) -> bool:
        """Check if an object matches this filter."""
        # Zone check
        if obj.zone not in self.zones:
            return False

        # Self-exclusion
        if self.exclude_self and source and obj.id == source.id:
            return False

        # Explicit exclusions
        if obj.id in self.exclude_ids:
            return False

        # Type checks
        obj_types = get_types(obj, state)
        if self.types is not None:
            if not self.types.intersection(obj_types):
                return False

        # Subtype checks
        if self.subtypes is not None:
            if not self.subtypes.intersection(obj.characteristics.subtypes):
                return False

        # Supertype checks
        if self.supertypes is not None:
            if not self.supertypes.intersection(obj.characteristics.supertypes):
                return False

        # Color checks
        obj_colors = get_colors(obj, state)
        if self.colors is not None:
            if not self.colors.intersection(obj_colors):
                return False

        if self.is_colorless:
            if obj_colors:  # Has any colors
                return False

        # Controller checks
        if self.controller == 'you' and source:
            if obj.controller != source.controller:
                return False
        elif self.controller == 'opponent' and source:
            if obj.controller == source.controller:
                return False

        # Ability checks
        if self.abilities:
            for ability in self.abilities:
                if not has_ability(obj, ability, state):
                    return False

        # Power/toughness checks (for creatures)
        if self.power_max is not None or self.power_min is not None:
            from .queries import get_power
            power = get_power(obj, state)
            if self.power_max is not None and power > self.power_max:
                return False
            if self.power_min is not None and power < self.power_min:
                return False

        if self.toughness_max is not None or self.toughness_min is not None:
            from .queries import get_toughness
            toughness = get_toughness(obj, state)
            if self.toughness_max is not None and toughness > self.toughness_max:
                return False
            if self.toughness_min is not None and toughness < self.toughness_min:
                return False

        # Mana value checks (Phase 5b cross-target: "same mana value")
        if self.mana_value_min is not None or self.mana_value_max is not None:
            chars = getattr(obj, 'characteristics', None)
            # Compute mana value from the printed mana_cost via ManaCost.
            # Done lazily here to avoid a top-of-file import cycle.
            try:
                from .mana import ManaCost
                cost = ManaCost.parse(getattr(chars, 'mana_cost', '') or '')
                mv = cost.mana_value
            except Exception:
                mv = 0
            if self.mana_value_min is not None and mv < self.mana_value_min:
                return False
            if self.mana_value_max is not None and mv > self.mana_value_max:
                return False

        # State checks
        if self.tapped is True and not obj.state.tapped:
            return False
        if self.untapped is True and obj.state.tapped:
            return False

        # Custom filter
        if self.custom_filter is not None:
            if not self.custom_filter(obj, state):
                return False

        return True


@dataclass
class TargetRequirement:
    """
    Specification for what targets a spell/ability needs.

    Examples:
        - "target creature" -> filter=creature_filter, count=1
        - "up to two target creatures" -> filter=creature_filter, count=2, count_type='up_to'
        - "any number of target creatures" -> filter=creature_filter, count=0, count_type='any_number'
    """
    filter: TargetFilter
    count: int = 1
    count_type: Literal['exactly', 'up_to', 'any_number'] = 'exactly'
    label: str = ""  # For UI: "target creature", "target opponent", etc.

    # For modal spells where this target may be optional
    optional: bool = False

    # For divided effects (e.g., "deal 3 damage divided among").
    # Either a literal int (fixed-damage burn like Twin Bolt's 2) or a
    # callable ``(state, caster_id) -> int`` for X-cost spells (Comet
    # Storm: X+1; Ureni: number of lands you control). Read by
    # ``priority._emit_cast_target_choice_step`` to emit a
    # ``divide_allocation`` PendingChoice at cast time.
    divide_amount: Optional[Any] = None

    def min_targets(self) -> int:
        """Minimum number of targets required."""
        if self.count_type == 'exactly':
            return self.count
        elif self.count_type == 'up_to':
            return 0 if self.optional else 1
        else:  # any_number
            return 0

    def max_targets(self) -> int:
        """Maximum number of targets allowed."""
        if self.count_type == 'any_number':
            return float('inf')
        return self.count


@dataclass
class Target:
    """A selected target."""
    id: str  # Object ID or player ID
    is_player: bool = False
    divided_amount: Optional[int] = None  # For divided effects


# Phase 5b cross-target support: a TargetRequirementBuilder is a callable
# that receives game state, the casting player, and the list of IDs already
# picked for earlier requirements, and returns a ``TargetRequirement`` whose
# filter encodes the cross-target constraint (e.g. "another target" excludes
# IDs already chosen, "different controllers" excludes the prior pick's
# controller, "same mana value" reads the prior pick's MV from state).
#
# ``CardDefinition.target_requirements`` may mix plain ``TargetRequirement``
# instances and these builders. ``priority._emit_cast_target_choice_step``
# resolves builders to a fresh ``TargetRequirement`` each time it advances
# to the next requirement in the chain.
#
# ``accumulated`` is shaped as a list of lists (one inner list per prior
# requirement, holding the chosen target IDs). Index ``[i]`` corresponds to
# requirement ``[i]`` in the spec — earlier requirements only.
TargetRequirementBuilder = Callable[
    [GameState, str, list[list[str]]],
    "TargetRequirement",
]


def resolve_target_requirement_spec(
    spec,
    state: GameState,
    controller_id: str,
    accumulated_ids: list,
) -> "TargetRequirement":
    """Coerce a ``target_requirements`` spec entry into a ``TargetRequirement``.

    ``spec`` may be a plain ``TargetRequirement`` (back-compat path) or a
    ``TargetRequirementBuilder`` callable. Builders are invoked with the
    state, the casting player id, and the picks collected for earlier
    requirements; the returned ``TargetRequirement`` is used verbatim.

    This indirection lets cross-target constraints ("another target",
    "different controllers", "same mana value as the first target") be
    expressed declaratively without bloating ``TargetFilter`` with bespoke
    fields.
    """
    if isinstance(spec, TargetRequirement):
        return spec
    if callable(spec):
        return spec(state, controller_id, accumulated_ids)
    raise TypeError(
        f"target_requirements entry must be TargetRequirement or callable, "
        f"got {type(spec).__name__}"
    )


class TargetingSystem:
    """
    Handles all targeting logic.
    """

    def __init__(self, state: GameState):
        self.state = state

    def get_legal_targets(
        self,
        requirement: TargetRequirement,
        source: GameObject,
        source_controller: str
    ) -> list[str]:
        """
        Get all legal target IDs for a requirement.

        Checks:
        - Filter matches
        - Hexproof (can't be targeted by opponents)
        - Shroud (can't be targeted at all)
        - Protection (can't be targeted by sources with that quality)
        """
        legal = []

        # Check objects
        for obj_id, obj in self.state.objects.items():
            if not requirement.filter.matches(obj, self.state, source):
                continue

            if not self._can_target(obj, source, source_controller):
                continue

            legal.append(obj_id)

        # Check players if filter allows (for "any target" or player-targeting)
        if self._can_target_players(requirement.filter):
            for player_id in self.state.players:
                if requirement.filter.controller == 'you':
                    if player_id != source_controller:
                        continue
                elif requirement.filter.controller == 'opponent':
                    if player_id == source_controller:
                        continue

                # Check if player has hexproof (rare but exists)
                if not self._player_can_be_targeted(player_id, source, source_controller):
                    continue

                legal.append(player_id)

        return legal

    def _can_target(
        self,
        obj: GameObject,
        source: GameObject,
        source_controller: str
    ) -> bool:
        """Check if an object can be targeted by a source."""
        # Shroud - can't be targeted by anything
        if has_ability(obj, 'shroud', self.state):
            return False

        # Hexproof - can't be targeted by opponents
        if has_ability(obj, 'hexproof', self.state):
            if obj.controller != source_controller:
                return False

        # Ward - can still be targeted, but triggers a cost
        # (handled at resolution, not here)

        # Protection - check if source has protected quality
        if self._has_protection_from_source(obj, source):
            return False

        return True

    def _has_protection_from_source(
        self,
        obj: GameObject,
        source: GameObject
    ) -> bool:
        """
        Check if object has protection from the source.

        Protection from X means:
        - Can't be damaged by X
        - Can't be enchanted/equipped by X
        - Can't be blocked by X
        - Can't be targeted by X
        """
        # Check for protection abilities
        # Format: 'protection_from_white', 'protection_from_red', etc.
        source_colors = get_colors(source, self.state)

        color_protections = {
            Color.WHITE: 'protection_from_white',
            Color.BLUE: 'protection_from_blue',
            Color.BLACK: 'protection_from_black',
            Color.RED: 'protection_from_red',
            Color.GREEN: 'protection_from_green',
        }

        for color, protection_ability in color_protections.items():
            if color in source_colors:
                if has_ability(obj, protection_ability, self.state):
                    return True

        # Protection from creatures, artifacts, etc.
        source_types = get_types(source, self.state)

        type_protections = {
            CardType.CREATURE: 'protection_from_creatures',
            CardType.ARTIFACT: 'protection_from_artifacts',
            CardType.ENCHANTMENT: 'protection_from_enchantments',
        }

        for card_type, protection_ability in type_protections.items():
            if card_type in source_types:
                if has_ability(obj, protection_ability, self.state):
                    return True

        # Protection from everything (rare)
        if has_ability(obj, 'protection_from_everything', self.state):
            return True

        return False

    def _can_target_players(self, filter: TargetFilter) -> bool:
        """Check if a filter can target players."""
        # If no type restrictions, can target players (e.g., target_player)
        if filter.types is None:
            return True

        # "Any target" filters explicitly opt in to player targeting even
        # though they list permitted object types (CREATURE + PLANESWALKER).
        if filter.includes_players:
            return True

        # Can't target players if specific permanent types required
        return False

    def _player_can_be_targeted(
        self,
        player_id: str,
        source: GameObject,
        source_controller: str
    ) -> bool:
        """Check if a player can be targeted."""
        # Players can have hexproof (e.g., Leyline of Sanctity)
        # This would be tracked as an ability on the player or via emblems
        # For now, players can always be targeted
        return True

    def is_target_legal(
        self,
        target: Target,
        requirement: TargetRequirement,
        source: GameObject,
        source_controller: str
    ) -> bool:
        """Check if a specific target is still legal."""
        if target.is_player:
            return self._player_can_be_targeted(target.id, source, source_controller)

        if target.id not in self.state.objects:
            return False

        obj = self.state.objects[target.id]

        # Check filter still matches
        if not requirement.filter.matches(obj, self.state, source):
            return False

        # Check targeting restrictions
        if not self._can_target(obj, source, source_controller):
            return False

        return True

    def validate_targets(
        self,
        targets: list[Target],
        requirement: TargetRequirement,
        source: GameObject,
        source_controller: str
    ) -> tuple[bool, list[Target]]:
        """
        Validate a list of selected targets.

        Returns:
            (all_valid, legal_targets) - all_valid is True if targets are valid,
            legal_targets contains only the still-legal targets
        """
        legal = []

        for target in targets:
            if self.is_target_legal(target, requirement, source, source_controller):
                legal.append(target)

        # Check count requirements
        count = len(legal)

        if requirement.count_type == 'exactly':
            if count != requirement.count:
                return (False, legal)
        elif requirement.count_type == 'up_to':
            if count > requirement.count:
                return (False, legal)
        # 'any_number' always valid for count

        # If we had targets but now have none, that's a problem
        if len(targets) > 0 and len(legal) == 0:
            return (False, legal)

        return (True, legal)


# Convenience filter constructors

def creature_filter(**kwargs) -> TargetFilter:
    """Create a filter for creatures."""
    return TargetFilter(
        types={CardType.CREATURE},
        **kwargs
    )


def permanent_filter(**kwargs) -> TargetFilter:
    """Create a filter for any permanent."""
    return TargetFilter(
        types={CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT,
               CardType.LAND, CardType.PLANESWALKER},
        **kwargs
    )


def player_filter(controller: Literal['you', 'opponent', 'any'] = 'any') -> TargetFilter:
    """Create a filter for players."""
    return TargetFilter(
        types=None,  # No type restriction allows players
        controller=controller,
        zones=[]  # Players aren't in zones
    )


def any_target_filter(**kwargs) -> TargetFilter:
    """
    Create a filter for "any target" (creature, player, or planeswalker).
    """
    return TargetFilter(
        types={CardType.CREATURE, CardType.PLANESWALKER},
        zones=[ZoneType.BATTLEFIELD],
        includes_players=True,
        **kwargs
    )


def spell_filter(**kwargs) -> TargetFilter:
    """Create a filter for spells on the stack."""
    return TargetFilter(
        zones=[ZoneType.STACK],
        **kwargs
    )


def card_in_graveyard_filter(**kwargs) -> TargetFilter:
    """Create a filter for cards in graveyards."""
    return TargetFilter(
        zones=[ZoneType.GRAVEYARD],
        **kwargs
    )


# Convenience requirement constructors

def target_creature(count: int = 1, *, label: Optional[str] = None, **filter_kwargs) -> TargetRequirement:
    """'Target creature' requirement.

    ``label`` overrides the auto-generated label string ("target creature" /
    "target N creatures"); leaving it None falls back to the default.
    """
    return TargetRequirement(
        filter=creature_filter(**filter_kwargs),
        count=count,
        label=label if label is not None else (
            f"target creature" if count == 1 else f"target {count} creatures"
        ),
    )


def target_any(count: int = 1, **filter_kwargs) -> TargetRequirement:
    """'Any target' requirement (creature, player, or planeswalker)."""
    return TargetRequirement(
        filter=any_target_filter(**filter_kwargs),
        count=count,
        label="any target" if count == 1 else f"{count} targets"
    )


def target_player(controller: Literal['you', 'opponent', 'any'] = 'any') -> TargetRequirement:
    """'Target player' or 'target opponent' requirement."""
    label = "target player"
    if controller == 'opponent':
        label = "target opponent"
    elif controller == 'you':
        label = "yourself"

    return TargetRequirement(
        filter=player_filter(controller),
        count=1,
        label=label
    )


def target_spell(**filter_kwargs) -> TargetRequirement:
    """'Target spell' requirement."""
    return TargetRequirement(
        filter=spell_filter(**filter_kwargs),
        count=1,
        label="target spell"
    )


# ---------------------------------------------------------------------------
# Phase 5b cross-target builders
#
# Common ``TargetRequirementBuilder`` callables for cards that have
# inter-target constraints. Each returns a callable suitable for placing
# directly inside ``CardDefinition.target_requirements``.
# ---------------------------------------------------------------------------


def another_target_creature(
    *,
    count: int = 1,
    count_type: Literal['exactly', 'up_to', 'any_number'] = 'exactly',
    label: Optional[str] = None,
    optional: bool = False,
    prior_index: int = 0,
    **filter_kwargs,
) -> "TargetRequirementBuilder":
    """Builder for "another target creature" — excludes IDs picked for an
    earlier requirement.

    ``prior_index`` selects which earlier requirement's picks to exclude
    (defaults to the first requirement). Useful when the previous req
    selected a "your creature" and this one selects "another target creature"
    that must differ from it.

    Pass ``optional=True`` for "up to one/two other target creature" — the
    UI/AI may submit an empty selection. ``optional`` is forwarded onto the
    underlying ``TargetRequirement`` which lowers ``min_targets()`` to 0.
    """
    def _build(state, controller_id, accumulated_ids):
        excluded = set(accumulated_ids[prior_index]) if prior_index < len(accumulated_ids) else set()
        # Merge with any user-supplied exclude_ids. Copy the dict so the
        # builder is idempotent (callers may reuse the same builder across
        # multiple casts; pop() on the shared dict would erase exclude_ids
        # from the second cast onward).
        local_kwargs = dict(filter_kwargs)
        merged_excludes = set(local_kwargs.pop('exclude_ids', set())) | excluded
        kwargs = dict(local_kwargs, exclude_ids=merged_excludes)
        return TargetRequirement(
            filter=creature_filter(**kwargs),
            count=count,
            count_type=count_type,
            optional=optional,
            label=label or (f"another target creature" if count == 1
                            else f"{count} other target creatures"),
        )
    return _build


def target_creature_different_controller(
    *,
    label: Optional[str] = None,
    prior_index: int = 0,
    **filter_kwargs,
) -> "TargetRequirementBuilder":
    """Builder for "target creature controlled by a different player" —
    excludes any creature controlled by the controller of the earlier pick.

    The exclusion is implemented via a ``custom_filter`` because the
    static ``controller='you'/'opponent'`` axis is computed relative to
    the spell's source, not relative to a prior pick.
    """
    def _build(state, controller_id, accumulated_ids):
        prior_ids = accumulated_ids[prior_index] if prior_index < len(accumulated_ids) else []
        forbidden_controllers: set = set()
        for tid in prior_ids:
            obj = state.objects.get(tid)
            if obj is not None:
                forbidden_controllers.add(obj.controller)

        existing_custom = filter_kwargs.pop('custom_filter', None)

        def _diff_controller(obj, st, _existing=existing_custom, _forbidden=forbidden_controllers):
            if obj.controller in _forbidden:
                return False
            if _existing is not None:
                return _existing(obj, st)
            return True

        return TargetRequirement(
            filter=creature_filter(custom_filter=_diff_controller, **filter_kwargs),
            count=1,
            label=label or "target creature controlled by a different player",
        )
    return _build


def target_with_matching_mana_value(
    *,
    base_filter_factory: Callable[..., TargetFilter] = permanent_filter,
    prior_index: int = 0,
    label: Optional[str] = None,
    count: int = 1,
    **filter_kwargs,
) -> "TargetRequirementBuilder":
    """Builder for "target X with the same mana value as the previous target".

    ``base_filter_factory`` is one of the filter helpers (creature_filter,
    permanent_filter, etc.) used to build the constrained filter. The
    builder pins ``mana_value_min == mana_value_max`` to the prior pick's
    mana value so only equal-MV targets pass.
    """
    def _build(state, controller_id, accumulated_ids):
        prior_ids = accumulated_ids[prior_index] if prior_index < len(accumulated_ids) else []
        mv: Optional[int] = None
        for tid in prior_ids:
            obj = state.objects.get(tid)
            if obj is not None:
                try:
                    from .mana import ManaCost
                    cost_str = getattr(obj.characteristics, 'mana_cost', '') or ''
                    mv = ManaCost.parse(cost_str).mana_value
                except Exception:
                    mv = None
                if mv is not None:
                    break

        kwargs = dict(filter_kwargs)
        if mv is not None:
            kwargs['mana_value_min'] = mv
            kwargs['mana_value_max'] = mv

        return TargetRequirement(
            filter=base_filter_factory(**kwargs),
            count=count,
            label=label or (f"target with mana value {mv}" if mv is not None
                            else "target with matching mana value"),
        )
    return _build
