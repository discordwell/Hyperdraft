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
    # Phase 5b name-match: "another permanent you control with the same name"
    # / "Room you don't already control with the same name". When populated,
    # ``TargetFilter.matches()`` rejects any object whose printed ``name``
    # (or characteristics.name fallback) is in the set. Used by:
    #   - WOE The Apprentice's Folly  (Saga I/II): exclude names matching
    #     any token the caster controls.
    #   - WOE Yenna, Redtooth Regent  ({2},{T}): exclude names matching any
    #     OTHER permanent the caster controls.
    # See ``target_without_same_name_as_your_tokens`` /
    # ``target_without_same_name_as_other_permanents`` builders below.
    exclude_names: set[str] = field(default_factory=set)

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

        # Name-collision exclusions ("same name as a token you control",
        # "same name as another permanent you control"). The caller-side
        # builder snapshots the offending names at choice-emit time, so the
        # matcher only does the membership check here. Falls back gracefully
        # when name is missing.
        if self.exclude_names:
            obj_name = getattr(obj, "name", None)
            if obj_name is None:
                chars = getattr(obj, "characteristics", None)
                obj_name = getattr(chars, "name", None) if chars is not None else None
            if obj_name is not None and obj_name in self.exclude_names:
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

    def describe(self) -> str:
        """
        Human-readable predicate, surfaced to the client via
        PendingChoice.target_metadata.predicate_description so the
        targeting overlay pill can render labels like
        "creature with power 3 or less" without parsing card text.

        The output is composed from the populated flag fields. Engines
        that add custom predicate kinds (via custom_filter) should set
        a fallback description in the filter's caller — we don't try
        to introspect arbitrary callables.
        """
        parts: list[str] = []

        # Controller scope ("opponent's", "your", or unspecified).
        if self.controller == 'opponent':
            parts.append("opponent's")
        elif self.controller == 'you':
            parts.append('your')

        # Color hints (red, blue, ...).
        if self.colors:
            parts.append('/'.join(c.name.lower() for c in self.colors))
        elif self.is_colorless:
            parts.append('colorless')

        # Type / subtype noun. Falls back to "target" when nothing's set.
        if self.types:
            type_names = sorted(t.name.lower() for t in self.types)
            noun = ' or '.join(type_names)
        elif self.includes_players and not self.types:
            noun = 'any target'
        else:
            noun = 'target'
        parts.append(noun)

        if self.subtypes:
            parts.append('(' + ' or '.join(sorted(self.subtypes)) + ')')

        # State + stat filters in a parenthetical aside if any.
        modifiers: list[str] = []
        if self.power_max is not None and self.power_min is None:
            modifiers.append(f'power ≤ {self.power_max}')
        elif self.power_min is not None and self.power_max is None:
            modifiers.append(f'power ≥ {self.power_min}')
        elif self.power_max is not None and self.power_min is not None:
            modifiers.append(f'power {self.power_min}-{self.power_max}')
        if self.toughness_max is not None and self.toughness_min is None:
            modifiers.append(f'toughness ≤ {self.toughness_max}')
        elif self.toughness_min is not None and self.toughness_max is None:
            modifiers.append(f'toughness ≥ {self.toughness_min}')
        if self.mana_value_max is not None and self.mana_value_min is None:
            modifiers.append(f'mana value ≤ {self.mana_value_max}')
        elif self.mana_value_min is not None and self.mana_value_max is None:
            modifiers.append(f'mana value ≥ {self.mana_value_min}')
        if self.tapped is True:
            modifiers.append('tapped')
        if self.untapped is True:
            modifiers.append('untapped')
        if self.attacking:
            modifiers.append('attacking')
        if self.blocking:
            modifiers.append('blocking')
        if self.abilities:
            modifiers.append('with ' + ', '.join(self.abilities))

        if modifiers:
            parts.append('(' + ', '.join(modifiers) + ')')

        # exclude_self → "another"
        if self.exclude_self:
            parts.insert(0, 'another')

        return ' '.join(parts).strip()


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


def target_same_opponent_creature(
    *,
    label: Optional[str] = None,
    prior_index: int = 0,
    **filter_kwargs,
) -> "TargetRequirementBuilder":
    """Builder for "target creature controlled by the same opponent as the
    previous target".

    Used by cards like DSK ``Trial of Agony`` where the first requirement
    picks "target creature an opponent controls" and the second requirement
    must pick ANOTHER creature controlled by THAT SAME opponent.

    Reads the prior pick's controller from state, then builds a filter that:
      - Excludes the prior pick's ID (you need a DIFFERENT creature).
      - Requires the matched creature's controller equals the prior pick's
        controller (the same opponent).

    Returns a ``TargetRequirementBuilder``. Place this second in the
    ``target_requirements`` list; the first slot should use a builder or
    plain requirement that picks one opponent creature.
    """
    def _build(state, controller_id, accumulated_ids):
        prior_ids = accumulated_ids[prior_index] if prior_index < len(accumulated_ids) else []
        # Identify the controller of the prior pick.
        target_controller: Optional[str] = None
        for tid in prior_ids:
            obj = state.objects.get(tid)
            if obj is not None and obj.controller is not None:
                target_controller = obj.controller
                break

        local_kwargs = dict(filter_kwargs)
        existing_custom = local_kwargs.pop('custom_filter', None)
        merged_excludes = set(local_kwargs.pop('exclude_ids', set())) | set(prior_ids)

        def _same_controller(obj, st,
                             _wanted=target_controller,
                             _existing=existing_custom):
            if _wanted is not None and obj.controller != _wanted:
                return False
            if _existing is not None:
                return _existing(obj, st)
            return True

        return TargetRequirement(
            filter=creature_filter(
                custom_filter=_same_controller,
                exclude_ids=merged_excludes,
                **local_kwargs,
            ),
            count=1,
            label=label or "another creature controlled by the same opponent",
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


# ---------------------------------------------------------------------------
# Phase 5b name-collision builders
#
# Cards that say "target X that doesn't have the same name as Y" need their
# legal-target list to exclude any same-name collision at choice-emit time.
# Two patterns appear in the live card sets:
#
#   1. "doesn't have the same name as a token you control"      — Apprentice's Folly
#   2. "doesn't have the same name as another permanent you control" — Yenna
#
# Both helpers snapshot the offending names from the casting player's board
# state at evaluation time, then build a ``TargetRequirement`` whose
# ``TargetFilter.exclude_names`` is populated with those names. The matcher
# then rejects any candidate whose ``name`` is in the set. Because the
# offending name set is captured at request time, late-arriving permanents
# don't retroactively invalidate a target that was legal when emitted.
#
# These builders are designed to be drop-in callable entries inside
# ``CardDefinition.target_requirements`` for cards that route through
# ``priority._emit_cast_target_choice_step``. They also expose the
# underlying name-collection helpers (``_names_of_your_tokens`` /
# ``_names_of_your_other_permanents``) for activated-ability paths that
# build their own PendingChoice via ``pending_choice_helpers``.
# ---------------------------------------------------------------------------


def _names_of_your_tokens(state: GameState, controller_id: str) -> set[str]:
    """Return the set of printed names of tokens the controller has on the
    battlefield. Used by the Apprentice's Folly builder."""
    names: set[str] = set()
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.controller != controller_id:
            continue
        # Token detection: object.state.is_token OR characteristics.is_token,
        # with fallbacks for older shapes.
        is_token = bool(getattr(getattr(obj, "state", None), "is_token", False))
        if not is_token:
            is_token = bool(getattr(obj, "is_token", False))
        if not is_token:
            chars = getattr(obj, "characteristics", None)
            is_token = bool(getattr(chars, "is_token", False)) if chars is not None else False
        if not is_token:
            continue
        nm = getattr(obj, "name", None)
        if nm is None:
            chars = getattr(obj, "characteristics", None)
            nm = getattr(chars, "name", None) if chars is not None else None
        if nm:
            names.add(nm)
    return names


def _names_of_your_other_permanents(
    state: GameState, controller_id: str, *, source_id: Optional[str] = None,
) -> set[str]:
    """Return the set of printed names of permanents the controller has on
    the battlefield, EXCLUDING ``source_id`` (the activator / the source of
    the target requirement). Used by Yenna's builder so the activator's own
    name doesn't poison its own target pool.

    Note: this returns the UNFILTERED set of names. For per-candidate
    "no other permanent with the same name as me" filtering, see
    ``has_other_permanent_with_same_name`` which compares a candidate's
    name against every other permanent (excluding the candidate itself
    AND optionally ``source_id``) and returns True if a name-collision
    exists.
    """
    names: set[str] = set()
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.controller != controller_id:
            continue
        if source_id is not None and obj.id == source_id:
            continue
        nm = getattr(obj, "name", None)
        if nm is None:
            chars = getattr(obj, "characteristics", None)
            nm = getattr(chars, "name", None) if chars is not None else None
        if nm:
            names.add(nm)
    return names


def has_other_permanent_with_same_name(
    candidate: GameObject,
    state: GameState,
    *,
    controller_id: str,
    source_id: Optional[str] = None,
) -> bool:
    """Return True if ANY permanent OTHER than ``candidate`` (and other than
    ``source_id`` if provided) controlled by ``controller_id`` shares the
    candidate's printed name.

    This is the correct per-candidate predicate for "target X that doesn't
    have the same name as another permanent you control" — the "another"
    in the rule means "different from the target". So we sweep all
    controlled permanents, skip the candidate itself (and optionally the
    source), and check for any name match.

    Used by ``target_without_same_name_as_other_permanents`` via a
    ``custom_filter`` so the per-candidate logic runs at filter time.
    """
    cand_name = getattr(candidate, "name", None)
    if cand_name is None:
        chars = getattr(candidate, "characteristics", None)
        cand_name = getattr(chars, "name", None) if chars is not None else None
    if not cand_name:
        return False
    for obj in state.objects.values():
        if obj.id == candidate.id:
            continue
        if source_id is not None and obj.id == source_id:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if obj.controller != controller_id:
            continue
        other_name = getattr(obj, "name", None)
        if other_name is None:
            chars = getattr(obj, "characteristics", None)
            other_name = getattr(chars, "name", None) if chars is not None else None
        if other_name == cand_name:
            return True
    return False


def target_without_same_name_as_your_tokens(
    *,
    kind: Literal['creature', 'permanent', 'enchantment', 'nontoken_creature'] = 'creature',
    count: int = 1,
    label: Optional[str] = None,
    require_nontoken: bool = True,
    **filter_kwargs,
) -> "TargetRequirementBuilder":
    """Builder for "target X you control that doesn't have the same name as
    a token you control".

    Used by WOE The Apprentice's Folly (Saga I/II): "Choose target nontoken
    creature you control that doesn't have the same name as a token you
    control."

    The builder snapshots the names of the controller's tokens at emit time
    and populates ``exclude_names`` on the resulting filter. Setting
    ``require_nontoken=True`` (default) additionally filters out any token
    candidate (necessary for the "nontoken" qualifier).

    Args:
        kind: Underlying filter family. ``'creature'`` for creatures only,
            ``'enchantment'`` for enchantments only, ``'permanent'`` for any
            permanent type, ``'nontoken_creature'`` is an alias for
            ``'creature' + require_nontoken=True``.
        count: Targets required (default 1).
        label: Override the prompt label.
        require_nontoken: If True (default), reject token candidates via a
            ``custom_filter``. Disables the "is token" pass-through. Use
            False for "another permanent you control with the same name"
            patterns that don't include the nontoken qualifier.
        **filter_kwargs: Forwarded to the underlying filter factory.
    """
    if kind == 'nontoken_creature':
        kind = 'creature'
        require_nontoken = True

    def _build(state, controller_id, accumulated_ids):
        excluded_names = _names_of_your_tokens(state, controller_id)
        local_kwargs = dict(filter_kwargs)
        merged = set(local_kwargs.pop('exclude_names', set())) | excluded_names
        # Default to "you control" if the caller didn't override. The
        # Apprentice's Folly explicitly says "target nontoken creature you
        # control" — controller='you' is the typical wiring.
        local_kwargs.setdefault('controller', 'you')

        existing_custom = local_kwargs.pop('custom_filter', None)
        if require_nontoken:
            def _nontoken(obj, st, _existing=existing_custom):
                is_token = bool(getattr(getattr(obj, "state", None), "is_token", False))
                if not is_token:
                    is_token = bool(getattr(obj, "is_token", False))
                if not is_token:
                    chars = getattr(obj, "characteristics", None)
                    is_token = bool(getattr(chars, "is_token", False)) if chars is not None else False
                if is_token:
                    return False
                if _existing is not None:
                    return _existing(obj, st)
                return True
            local_kwargs['custom_filter'] = _nontoken
        elif existing_custom is not None:
            local_kwargs['custom_filter'] = existing_custom

        if kind == 'creature':
            tf = creature_filter(exclude_names=merged, **local_kwargs)
        elif kind == 'enchantment':
            ctrl = local_kwargs.pop('controller', 'any')
            cf = local_kwargs.pop('custom_filter', None)
            tf = TargetFilter(
                types={CardType.ENCHANTMENT},
                controller=ctrl,
                exclude_names=merged,
                custom_filter=cf,
                **local_kwargs,
            )
        else:  # 'permanent'
            tf = permanent_filter(exclude_names=merged, **local_kwargs)

        return TargetRequirement(
            filter=tf,
            count=count,
            label=label or (
                f"target {kind} you control without same name as a token you control"
            ),
        )
    return _build


def target_without_same_name_as_other_permanents(
    *,
    kind: Literal['creature', 'permanent', 'enchantment'] = 'enchantment',
    count: int = 1,
    label: Optional[str] = None,
    source_id: Optional[str] = None,
    **filter_kwargs,
) -> "TargetRequirementBuilder":
    """Builder for "target X you control that doesn't have the same name as
    another permanent you control".

    Used by WOE Yenna, Redtooth Regent ({2},{T}): "Choose target enchantment
    you control that doesn't have the same name as another permanent you
    control."

    The builder snapshots the names of every permanent the controller
    controls (excluding ``source_id`` if provided — typically Yenna herself,
    so she doesn't poison her own target pool with her own name) and pins
    them on the filter's ``exclude_names`` set.

    Args:
        kind: ``'enchantment'`` (Yenna), ``'creature'``, or ``'permanent'``.
        count: Targets required (default 1).
        label: Override the prompt label.
        source_id: When set, the named object is excluded from the
            name-snapshot so the source's own name doesn't gate its target
            pool. (Used for Yenna: Yenna is "another permanent you control"
            relative to the chosen enchantment, but her name shouldn't make
            an enchantment named the same as Yenna unselectable when the
            enchantment is Yenna herself.) See builder source for details.
        **filter_kwargs: Forwarded to the underlying filter factory.
    """
    def _build(state, controller_id, accumulated_ids):
        local_kwargs = dict(filter_kwargs)
        local_kwargs.setdefault('controller', 'you')
        existing_custom = local_kwargs.pop('custom_filter', None)

        # Per-candidate name-collision predicate: a candidate X is rejected
        # if any OTHER permanent the controller controls (excluding X and
        # excluding ``source_id`` if set) shares X's printed name. This
        # matches the MTG-rule semantics of "another permanent you control"
        # — the "another" is relative to the target, not to the source.
        def _no_other_with_same_name(cand, st, _existing=existing_custom,
                                     _ctrl=controller_id, _src=source_id):
            if has_other_permanent_with_same_name(
                cand, st, controller_id=_ctrl, source_id=_src,
            ):
                return False
            if _existing is not None:
                return _existing(cand, st)
            return True

        local_kwargs['custom_filter'] = _no_other_with_same_name

        if kind == 'enchantment':
            ctrl = local_kwargs.pop('controller', 'any')
            cf = local_kwargs.pop('custom_filter', None)
            tf = TargetFilter(
                types={CardType.ENCHANTMENT},
                controller=ctrl,
                custom_filter=cf,
                **local_kwargs,
            )
        elif kind == 'creature':
            tf = creature_filter(**local_kwargs)
        else:  # 'permanent'
            tf = permanent_filter(**local_kwargs)

        return TargetRequirement(
            filter=tf,
            count=count,
            label=label or (
                f"target {kind} you control without same name as another permanent you control"
            ),
        )
    return _build
