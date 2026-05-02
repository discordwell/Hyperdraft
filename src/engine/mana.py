"""
Hyperdraft Mana System

Handles mana costs, mana pools, and mana payment.
Supports standard MTG mana syntax: {W}, {U}, {B}, {R}, {G}, {C}, {X}, {1}, {2}, etc.
Also supports hybrid {W/U}, Phyrexian {W/P}, and snow {S}.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum, auto

from .types import CardType, Color, GameState

# Type alias: a restriction is a predicate over a "card-like" object (typically
# a CardDefinition or GameObject). It returns True if this card may be paid for
# with the restricted mana unit. Receiving an arbitrary object lets callers pass
# either the in-flight ``GameObject`` (for printed characteristics) or its
# ``CardDefinition`` — whichever they have on hand.
RestrictionFn = Callable[[Any], bool]


class ManaType(Enum):
    """All possible mana types."""
    WHITE = 'W'
    BLUE = 'U'
    BLACK = 'B'
    RED = 'R'
    GREEN = 'G'
    COLORLESS = 'C'  # Specifically colorless (Eldrazi, etc.)
    SNOW = 'S'


@dataclass
class ManaUnit:
    """A single unit of mana in a pool.

    ``restriction`` is an optional predicate that gates spending this unit on
    a spell. When ``None`` the unit is unrestricted. When set, the unit may
    only be spent on a card for which ``restriction(card_def)`` returns True.
    Restricted units are only spent on a spell-cast path that passes
    ``for_card=...`` to ``ManaPool.can_pay`` / ``pay``; on cost-payment paths
    that don't supply a card (e.g. activated-ability mana costs), restricted
    units are skipped.

    ``restriction_text`` is a human-readable description of the rule, used for
    debug printing and the cast UI.
    """
    color: ManaType
    snow: bool = False
    # Legacy free-form restriction tags retained for compatibility with older
    # call sites; treated as informational only.
    restrictions: list[str] = field(default_factory=list)
    source_id: Optional[str] = None
    # Spend-restriction predicate. None = unrestricted.
    restriction: Optional[RestrictionFn] = None
    restriction_text: str = ""


@dataclass
class ManaCost:
    """Parsed mana cost structure."""
    white: int = 0
    blue: int = 0
    black: int = 0
    red: int = 0
    green: int = 0
    colorless: int = 0  # Specifically colorless ({C})
    generic: int = 0    # Can be paid with any color ({1}, {2}, etc.)
    snow: int = 0       # Snow mana requirement ({S})
    x_count: int = 0    # Number of X in the cost

    # Hybrid costs: list of (option1, option2) tuples
    # e.g., {W/U} becomes [('W', 'U')]
    hybrid: list[tuple[str, str]] = field(default_factory=list)

    # Phyrexian costs: list of colors that can be paid with 2 life
    # e.g., {W/P} becomes ['W']
    phyrexian: list[str] = field(default_factory=list)

    @property
    def mana_value(self) -> int:
        """Calculate converted mana cost / mana value."""
        return (
            self.white + self.blue + self.black + self.red + self.green +
            self.colorless + self.generic + self.snow +
            len(self.hybrid) + len(self.phyrexian)
            # X counts as 0 for mana value when not on stack
        )

    @property
    def colors(self) -> set[Color]:
        """Get colors in this mana cost."""
        colors = set()
        if self.white > 0:
            colors.add(Color.WHITE)
        if self.blue > 0:
            colors.add(Color.BLUE)
        if self.black > 0:
            colors.add(Color.BLACK)
        if self.red > 0:
            colors.add(Color.RED)
        if self.green > 0:
            colors.add(Color.GREEN)

        # Check hybrid costs for colors
        color_map = {'W': Color.WHITE, 'U': Color.BLUE, 'B': Color.BLACK,
                     'R': Color.RED, 'G': Color.GREEN}
        for opt1, opt2 in self.hybrid:
            if opt1 in color_map:
                colors.add(color_map[opt1])
            if opt2 in color_map:
                colors.add(color_map[opt2])

        # Check phyrexian costs
        for p in self.phyrexian:
            if p in color_map:
                colors.add(color_map[p])

        return colors

    def is_free(self) -> bool:
        """Check if this cost is free (no mana required)."""
        return (
            self.white == 0 and self.blue == 0 and self.black == 0 and
            self.red == 0 and self.green == 0 and self.colorless == 0 and
            self.generic == 0 and self.snow == 0 and self.x_count == 0 and
            len(self.hybrid) == 0 and len(self.phyrexian) == 0
        )

    @classmethod
    def parse(cls, cost_string: str) -> 'ManaCost':
        """
        Parse a mana cost string.

        Examples:
            "{W}" -> 1 white
            "{2}{U}{U}" -> 2 generic, 2 blue
            "{X}{R}{R}" -> X, 2 red
            "{W/U}" -> 1 hybrid white/blue
            "{G/P}" -> 1 phyrexian green
            "{C}" -> 1 colorless
            "{S}" -> 1 snow
        """
        if not cost_string:
            return cls()

        cost = cls()

        # Find all mana symbols in braces
        symbols = re.findall(r'\{([^}]+)\}', cost_string)

        for symbol in symbols:
            symbol = symbol.upper()

            # Hybrid mana (W/U, 2/W, etc.)
            if '/' in symbol:
                parts = symbol.split('/')
                if parts[1] == 'P':
                    # Phyrexian mana
                    cost.phyrexian.append(parts[0])
                else:
                    # Regular hybrid
                    cost.hybrid.append((parts[0], parts[1]))

            # Colored mana
            elif symbol == 'W':
                cost.white += 1
            elif symbol == 'U':
                cost.blue += 1
            elif symbol == 'B':
                cost.black += 1
            elif symbol == 'R':
                cost.red += 1
            elif symbol == 'G':
                cost.green += 1

            # Colorless
            elif symbol == 'C':
                cost.colorless += 1

            # Snow
            elif symbol == 'S':
                cost.snow += 1

            # X
            elif symbol == 'X':
                cost.x_count += 1

            # Generic (numbers)
            elif symbol.isdigit():
                cost.generic += int(symbol)

        return cost

    def to_string(self) -> str:
        """Convert back to mana cost string."""
        parts = []

        # X costs first
        for _ in range(self.x_count):
            parts.append('{X}')

        # Generic
        if self.generic > 0:
            parts.append(f'{{{self.generic}}}')

        # Hybrid
        for opt1, opt2 in self.hybrid:
            parts.append(f'{{{opt1}/{opt2}}}')

        # Phyrexian
        for p in self.phyrexian:
            parts.append(f'{{{p}/P}}')

        # Snow
        for _ in range(self.snow):
            parts.append('{S}')

        # Colorless
        for _ in range(self.colorless):
            parts.append('{C}')

        # WUBRG order
        for _ in range(self.white):
            parts.append('{W}')
        for _ in range(self.blue):
            parts.append('{U}')
        for _ in range(self.black):
            parts.append('{B}')
        for _ in range(self.red):
            parts.append('{R}')
        for _ in range(self.green):
            parts.append('{G}')

        return ''.join(parts) if parts else '{0}'


class ManaPool:
    """
    A player's mana pool.

    Tracks available mana with potential restrictions.
    """

    def __init__(self):
        self.mana: list[ManaUnit] = []

    def add(
        self,
        color: ManaType,
        amount: int = 1,
        snow: bool = False,
        restrictions: list[str] = None,
        source_id: str = None,
        *,
        restriction: Optional[RestrictionFn] = None,
        restriction_text: str = "",
    ):
        """Add mana to the pool.

        ``restriction`` (if set) marks each added unit with a spend-restriction
        predicate. ``restriction_text`` is a human-readable summary.
        """
        for _ in range(amount):
            self.mana.append(ManaUnit(
                color=color,
                snow=snow,
                restrictions=restrictions or [],
                source_id=source_id,
                restriction=restriction,
                restriction_text=restriction_text,
            ))

    def add_any_color(self, amount: int = 1, snow: bool = False, source_id: str = None):
        """Add mana that can be any color (stored as separate units)."""
        # For "any color" mana, we store it as a special marker
        # In practice, the player chooses the color when adding
        # For now, we'll need to handle this at a higher level
        pass

    def get_count(self, color: ManaType = None, snow_only: bool = False) -> int:
        """Count mana in pool, optionally filtered by color/snow."""
        count = 0
        for unit in self.mana:
            if color is not None and unit.color != color:
                continue
            if snow_only and not unit.snow:
                continue
            count += 1
        return count

    def total(self) -> int:
        """Total mana in pool."""
        return len(self.mana)

    def can_pay(
        self,
        cost: ManaCost,
        x_value: int = 0,
        *,
        for_card: Any = None,
    ) -> bool:
        """
        Check if the pool can pay a mana cost.

        Uses a greedy algorithm that tries to pay specific costs first,
        then generic with remaining mana.

        ``for_card`` is the card being cast (or its CardDefinition / GameObject).
        Restricted mana units only count toward payment when their restriction
        predicate returns True for ``for_card``. When ``for_card`` is None
        (e.g. paying an activated-ability mana cost), restricted units are
        not used.
        """
        return self._try_pay(cost, x_value, actually_pay=False, for_card=for_card)

    def pay(
        self,
        cost: ManaCost,
        x_value: int = 0,
        *,
        for_card: Any = None,
    ) -> bool:
        """
        Actually pay a mana cost, removing mana from pool.
        Returns True if successful, False if unable to pay.

        ``for_card`` semantics match ``can_pay``.
        """
        return self._try_pay(cost, x_value, actually_pay=True, for_card=for_card)

    def _unit_is_spendable(self, unit: ManaUnit, for_card: Any) -> bool:
        """Return True if ``unit`` can legally be spent on ``for_card``.

        Unrestricted units are always spendable. Restricted units are
        spendable only when ``for_card`` is supplied and the unit's
        restriction predicate returns True for it.
        """
        if unit.restriction is None:
            return True
        if for_card is None:
            return False
        try:
            return bool(unit.restriction(for_card))
        except Exception:
            return False

    def _try_pay(
        self,
        cost: ManaCost,
        x_value: int,
        actually_pay: bool,
        *,
        for_card: Any = None,
    ) -> bool:
        """
        Attempt to pay a cost.

        Algorithm:
        1. Pay specific colored costs (W, U, B, R, G)
        2. Pay colorless costs (C) with colorless mana
        3. Pay snow costs (S) with snow mana
        4. Pay hybrid costs (choosing cheaper option)
        5. Pay phyrexian costs (mana or life - for now, assume mana)
        6. Pay X costs
        7. Pay generic costs with remaining mana

        Within each step, restricted units are tried last so unrestricted mana
        is preserved for parts of the cost where it might be the only option.
        """
        # Work with a copy if not actually paying
        available = list(self.mana) if not actually_pay else self.mana

        def _candidate_indices(predicate: Callable[[ManaUnit], bool]) -> list[int]:
            """Return indices of spendable units satisfying ``predicate``,
            with unrestricted units listed before restricted ones so the
            greedy algorithm spends unrestricted mana first."""
            unrestricted: list[int] = []
            restricted: list[int] = []
            for i, unit in enumerate(available):
                if not predicate(unit):
                    continue
                if not self._unit_is_spendable(unit, for_card):
                    continue
                if unit.restriction is None:
                    unrestricted.append(i)
                else:
                    restricted.append(i)
            return unrestricted + restricted

        def remove_mana(color: ManaType, count: int, snow_required: bool = False) -> bool:
            """Remove specified mana from available pool."""
            def _pred(u: ManaUnit) -> bool:
                if u.color != color:
                    return False
                if snow_required and not u.snow:
                    return False
                return True

            indices = _candidate_indices(_pred)
            if len(indices) < count:
                return False

            to_remove = sorted(indices[:count], reverse=True)
            for i in to_remove:
                available.pop(i)
            return True

        def remove_any(count: int, snow_required: bool = False) -> bool:
            """Remove any mana from pool."""
            def _pred(u: ManaUnit) -> bool:
                if snow_required and not u.snow:
                    return False
                return True

            indices = _candidate_indices(_pred)
            if len(indices) < count:
                return False

            to_remove = sorted(indices[:count], reverse=True)
            for i in to_remove:
                available.pop(i)
            return True

        # 1. Pay colored costs
        color_map = {
            'white': ManaType.WHITE,
            'blue': ManaType.BLUE,
            'black': ManaType.BLACK,
            'red': ManaType.RED,
            'green': ManaType.GREEN,
        }

        for attr, mana_type in color_map.items():
            amount = getattr(cost, attr)
            if amount > 0:
                if not remove_mana(mana_type, amount):
                    return False

        # 2. Pay colorless costs
        if cost.colorless > 0:
            if not remove_mana(ManaType.COLORLESS, cost.colorless):
                return False

        # 3. Pay snow costs
        if cost.snow > 0:
            if not remove_any(cost.snow, snow_required=True):
                return False

        # 4. Pay hybrid costs (try to use what we have more of)
        for opt1, opt2 in cost.hybrid:
            opt1_type = self._symbol_to_type(opt1)
            opt2_type = self._symbol_to_type(opt2)

            # Try option 1 first
            if opt1_type and not remove_mana(opt1_type, 1):
                # Try option 2
                if opt2_type and not remove_mana(opt2_type, 1):
                    # Try generic if one option is a number
                    if opt1.isdigit():
                        if not remove_any(int(opt1)):
                            return False
                    elif opt2.isdigit():
                        if not remove_any(int(opt2)):
                            return False
                    else:
                        return False

        # 5. Pay phyrexian costs (for now, just try to pay with mana)
        for p in cost.phyrexian:
            p_type = self._symbol_to_type(p)
            if p_type and not remove_mana(p_type, 1):
                # Could pay with life instead - handle at higher level
                return False

        # 6. Pay X costs
        total_x = cost.x_count * x_value
        if total_x > 0:
            if not remove_any(total_x):
                return False

        # 7. Pay generic costs
        if cost.generic > 0:
            if not remove_any(cost.generic):
                return False

        # If we got here and actually paying, update self.mana
        if actually_pay:
            self.mana = available

        return True

    def _symbol_to_type(self, symbol: str) -> Optional[ManaType]:
        """Convert mana symbol to ManaType."""
        symbol_map = {
            'W': ManaType.WHITE,
            'U': ManaType.BLUE,
            'B': ManaType.BLACK,
            'R': ManaType.RED,
            'G': ManaType.GREEN,
            'C': ManaType.COLORLESS,
            'S': ManaType.SNOW,
        }
        return symbol_map.get(symbol.upper())

    def empty(self):
        """Empty the mana pool (end of phase/step)."""
        # Could trigger "mana burn" effects in old rules
        # Or "when mana empties" triggers
        self.mana.clear()

    def __repr__(self) -> str:
        counts = {}
        for unit in self.mana:
            key = unit.color.value
            if unit.snow:
                key = f"S{key}"
            counts[key] = counts.get(key, 0) + 1
        return f"ManaPool({counts})"


@dataclass
class LandManaSource:
    """Represents an untapped land that can produce mana."""
    land_id: str
    land_name: str
    produces: list[ManaType]  # What colors this land can produce
    is_snow: bool = False


@dataclass
class TapSolution:
    """A solution for how to tap lands to pay a cost."""
    lands_to_tap: list[str]  # Land IDs to tap
    mana_produced: dict[ManaType, int]  # What mana is produced
    is_unique: bool = True  # Whether this is the only valid solution


class ManaSystem:
    """
    High-level mana system that integrates with the game.

    Supports auto-tapping lands when there's no ambiguity,
    or prompting for land selection when multiple options exist.
    """

    # Basic land type to mana color mapping
    BASIC_LAND_MANA: dict[str, ManaType] = {
        'Plains': ManaType.WHITE,
        'Island': ManaType.BLUE,
        'Swamp': ManaType.BLACK,
        'Mountain': ManaType.RED,
        'Forest': ManaType.GREEN,
    }

    def __init__(self, game_state: GameState):
        self.state = game_state
        self.pools: dict[str, ManaPool] = {}  # player_id -> ManaPool

    def get_pool(self, player_id: str) -> ManaPool:
        """Get or create a player's mana pool."""
        if player_id not in self.pools:
            self.pools[player_id] = ManaPool()
        return self.pools[player_id]

    def get_untapped_lands(self, player_id: str) -> list[LandManaSource]:
        """Get all untapped lands a player controls that can produce mana."""
        sources = []
        battlefield = self.state.zones.get('battlefield')
        if not battlefield:
            return sources

        for obj_id in battlefield.objects:
            obj = self.state.objects.get(obj_id)
            if not obj:
                continue

            # Check if it's a land controlled by this player
            from .types import CardType
            if CardType.LAND not in obj.characteristics.types:
                continue
            if obj.controller != player_id:
                continue

            # Check if untapped
            if obj.state.tapped:
                continue

            # Determine what mana it produces
            produces = self._get_land_mana_production(obj)
            if produces:
                sources.append(LandManaSource(
                    land_id=obj.id,
                    land_name=obj.name,
                    produces=produces,
                    is_snow='Snow' in obj.characteristics.supertypes
                ))

        return sources

    def _get_land_mana_production(self, land_obj) -> list[ManaType]:
        """Determine what mana a land can produce."""
        produces = []

        # Check for basic land types in subtypes
        for subtype in land_obj.characteristics.subtypes:
            if subtype in self.BASIC_LAND_MANA:
                produces.append(self.BASIC_LAND_MANA[subtype])

        # If no subtypes found, check the name for basic lands
        if not produces:
            if land_obj.name in self.BASIC_LAND_MANA:
                produces.append(self.BASIC_LAND_MANA[land_obj.name])

        # If still no mana production, parse text for tap mana abilities
        if not produces and land_obj.card_def and land_obj.card_def.text:
            produces = self._parse_mana_abilities_from_text(land_obj.card_def.text)

        return produces

    def _parse_mana_abilities_from_text(self, text: str) -> list[ManaType]:
        """Parse mana production from land's rules text."""
        import re
        produces = []

        if not text:
            return produces

        # Map mana symbols to ManaType
        MANA_SYMBOL_MAP = {
            'W': ManaType.WHITE,
            'U': ManaType.BLUE,
            'B': ManaType.BLACK,
            'R': ManaType.RED,
            'G': ManaType.GREEN,
            'C': ManaType.COLORLESS,
        }

        # Match tap abilities: {T}: Add {X} or {T}: Add {X}{Y}...
        # Pattern matches: {T}: Add {R}, {T}: Add {G}{G}, etc.
        tap_add_pattern = r'\{T\}:\s*Add\s+(\{[WUBRGC]\}(?:\{[WUBRGC]\})*)'
        matches = re.findall(tap_add_pattern, text)

        for match in matches:
            # Extract individual mana symbols from the match
            symbols = re.findall(r'\{([WUBRGC])\}', match)
            for symbol in symbols:
                if symbol in MANA_SYMBOL_MAP:
                    mana_type = MANA_SYMBOL_MAP[symbol]
                    if mana_type not in produces:
                        produces.append(mana_type)

        # Also match "Add one mana of any color" pattern
        if re.search(r'Add one mana of any color', text, re.IGNORECASE):
            for mt in [ManaType.WHITE, ManaType.BLUE, ManaType.BLACK, ManaType.RED, ManaType.GREEN]:
                if mt not in produces:
                    produces.append(mt)

        return produces

    def get_available_mana(self, player_id: str) -> dict[ManaType, int]:
        """Get total available mana from untapped lands (potential, not in pool)."""
        sources = self.get_untapped_lands(player_id)
        available = {mt: 0 for mt in ManaType}

        for source in sources:
            # For lands that produce multiple colors, count each possibility
            # This is optimistic - actual payment may require choices
            for mana_type in source.produces:
                available[mana_type] += 1

        return available

    def can_cast(
        self,
        player_id: str,
        cost: ManaCost,
        x_value: int = 0,
        *,
        for_card: Any = None,
    ) -> bool:
        """
        Check if a player can pay a mana cost using their untapped lands.

        This checks potential mana from lands, not just the mana pool.
        ``for_card`` is the card being cast (or its CardDefinition); restricted
        mana in the pool only counts when its predicate matches.
        """
        # First check if pool already has enough
        pool = self.get_pool(player_id)
        if pool.can_pay(cost, x_value, for_card=for_card):
            return True

        # If the pool has restricted mana matching this card, attempt to pay
        # using a fresh combined view of pool + untapped lands. We don't
        # currently auto-tap restricted-mana sources here; restricted mana is
        # only honoured when it's already been added to the pool by an
        # explicit activation.
        sources = self.get_untapped_lands(player_id)
        if not sources:
            # No additional mana available from untapped lands; the pool check
            # above already failed.
            return False

        # Project untapped lands into a synthetic pool that still respects the
        # caller's existing pool restrictions, then test affordability.
        return self._can_pay_with_pool_and_lands(pool, sources, cost, x_value, for_card=for_card)

    def _can_pay_with_pool_and_lands(
        self,
        pool: 'ManaPool',
        sources: list['LandManaSource'],
        cost: ManaCost,
        x_value: int,
        *,
        for_card: Any = None,
    ) -> bool:
        """Check affordability using the existing pool plus potential land mana.

        Lands always produce unrestricted mana for purposes of this check
        (basic land tap abilities are unrestricted in the rules). Pool units
        retain their restrictions.
        """
        # Build a synthetic pool: copy current pool units (preserving restrictions),
        # then add one unit per untapped land (always unrestricted, picking the
        # first declared color as the produced color).
        synthetic = ManaPool()
        synthetic.mana = list(pool.mana)
        for source in sources:
            if not source.produces:
                continue
            # Take any single color the land produces — for affordability
            # this is conservative since multi-color lands could produce
            # more flexible color combinations than what we project.
            synthetic.add(source.produces[0], 1, snow=source.is_snow)
        return synthetic.can_pay(cost, x_value, for_card=for_card)

    def _can_pay_with_lands(self, sources: list[LandManaSource], cost: ManaCost, x_value: int = 0) -> bool:
        """Check if the given land sources can pay a cost."""
        # Build a simple availability count
        # For single-color lands, this is straightforward
        # For multi-color lands, we need to be smarter

        single_color_counts = {mt: 0 for mt in ManaType}
        multi_color_lands = []

        for source in sources:
            if len(source.produces) == 1:
                single_color_counts[source.produces[0]] += 1
            else:
                multi_color_lands.append(source)

        # Calculate what we need
        needed = {
            ManaType.WHITE: cost.white,
            ManaType.BLUE: cost.blue,
            ManaType.BLACK: cost.black,
            ManaType.RED: cost.red,
            ManaType.GREEN: cost.green,
            ManaType.COLORLESS: cost.colorless,
        }

        # Add X cost
        generic_needed = cost.generic + (cost.x_count * x_value)

        # First, try to pay colored costs with single-color lands
        remaining_single = dict(single_color_counts)
        for mana_type, amount in needed.items():
            if amount > 0:
                available = remaining_single[mana_type]
                used = min(available, amount)
                remaining_single[mana_type] -= used
                needed[mana_type] -= used

        # Check if we still need colored mana
        colored_still_needed = sum(needed.values())

        # Try to cover remaining colored needs with multi-color lands
        multi_available = len(multi_color_lands)

        # Total mana available for generic
        total_remaining = sum(remaining_single.values()) + multi_available - colored_still_needed

        # Can we cover colored needs with multi-color lands?
        if colored_still_needed > multi_available:
            return False

        # Can we cover generic needs?
        if generic_needed > total_remaining:
            return False

        return True

    def find_auto_tap_solution(self, player_id: str, cost: ManaCost, x_value: int = 0) -> Optional[TapSolution]:
        """
        Find lands to tap to pay a cost. Returns None if impossible.

        If there's only one way to pay, returns that solution with is_unique=True.
        If there are multiple ways, returns one solution with is_unique=False.
        """
        sources = self.get_untapped_lands(player_id)
        if not self._can_pay_with_lands(sources, cost, x_value):
            return None

        # Separate single-color and multi-color lands
        single_color: dict[ManaType, list[LandManaSource]] = {mt: [] for mt in ManaType}
        multi_color: list[LandManaSource] = []

        for source in sources:
            if len(source.produces) == 1:
                single_color[source.produces[0]].append(source)
            else:
                multi_color.append(source)

        lands_to_tap = []
        mana_produced = {mt: 0 for mt in ManaType}
        has_choices = False

        # Pay colored costs first, using single-color lands when possible
        color_needs = [
            (ManaType.WHITE, cost.white),
            (ManaType.BLUE, cost.blue),
            (ManaType.BLACK, cost.black),
            (ManaType.RED, cost.red),
            (ManaType.GREEN, cost.green),
        ]

        for mana_type, amount in color_needs:
            remaining = amount

            # Use single-color lands first
            while remaining > 0 and single_color[mana_type]:
                source = single_color[mana_type].pop(0)
                lands_to_tap.append(source.land_id)
                mana_produced[mana_type] += 1
                remaining -= 1

            # Use multi-color lands if needed
            while remaining > 0 and multi_color:
                # Find a multi-color land that produces this color
                for i, source in enumerate(multi_color):
                    if mana_type in source.produces:
                        lands_to_tap.append(source.land_id)
                        mana_produced[mana_type] += 1
                        multi_color.pop(i)
                        remaining -= 1
                        # Using multi-color for colored = potential choice
                        if len(source.produces) > 1:
                            has_choices = True
                        break
                else:
                    # No multi-color land produces this color - shouldn't happen if can_pay was true
                    return None

        # Pay colorless cost (C specifically)
        remaining_colorless = cost.colorless
        # Would need lands that produce specifically colorless - skip for now

        # Pay generic cost with any remaining lands
        generic_needed = cost.generic + (cost.x_count * x_value)

        # Use remaining single-color lands
        for mana_type in ManaType:
            while generic_needed > 0 and single_color[mana_type]:
                source = single_color[mana_type].pop(0)
                lands_to_tap.append(source.land_id)
                mana_produced[mana_type] += 1
                generic_needed -= 1

        # Use remaining multi-color lands
        while generic_needed > 0 and multi_color:
            source = multi_color.pop(0)
            lands_to_tap.append(source.land_id)
            # For generic, just pick first color
            mana_produced[source.produces[0]] += 1
            generic_needed -= 1
            if len(source.produces) > 1:
                has_choices = True

        # Check for ambiguity: if we have unused lands of the same colors we used,
        # there might be multiple valid solutions
        total_unused = sum(len(lands) for lands in single_color.values()) + len(multi_color)
        if total_unused > 0:
            # Check if any unused land produces colors we're using
            colors_used = {mt for mt, count in mana_produced.items() if count > 0}
            for mt in colors_used:
                if single_color[mt]:
                    has_choices = True
                    break

        return TapSolution(
            lands_to_tap=lands_to_tap,
            mana_produced=mana_produced,
            is_unique=not has_choices
        )

    def auto_tap_and_pay(
        self,
        player_id: str,
        cost: ManaCost,
        x_value: int = 0,
        *,
        for_card: Any = None,
    ) -> tuple[bool, Optional[TapSolution]]:
        """
        Automatically tap lands and pay a cost if there's no ambiguity.

        Returns (success, solution).
        - If successful and unambiguous: (True, solution with is_unique=True)
        - If successful but ambiguous: (False, solution with is_unique=False) - caller should prompt
        - If impossible: (False, None)
        """
        solution = self.find_auto_tap_solution(player_id, cost, x_value)
        if not solution:
            return (False, None)

        if not solution.is_unique:
            # Ambiguous - let caller decide whether to prompt or accept default
            return (False, solution)

        # Unambiguous - execute the taps and add mana to pool
        self._execute_tap_solution(player_id, solution)

        # Pay from pool
        pool = self.get_pool(player_id)
        pool.pay(cost, x_value, for_card=for_card)

        return (True, solution)

    def execute_tap_solution(
        self,
        player_id: str,
        solution: TapSolution,
        cost: ManaCost,
        x_value: int = 0,
        *,
        for_card: Any = None,
    ) -> bool:
        """Execute a specific tap solution (used when player selects lands manually)."""
        self._execute_tap_solution(player_id, solution)

        # Pay from pool
        pool = self.get_pool(player_id)
        return pool.pay(cost, x_value, for_card=for_card)

    def _execute_tap_solution(self, player_id: str, solution: TapSolution):
        """Actually tap the lands and add mana to pool."""
        pool = self.get_pool(player_id)

        for land_id in solution.lands_to_tap:
            obj = self.state.objects.get(land_id)
            if obj and not obj.state.tapped:
                # Tap the land
                obj.state.tapped = True

        # Add produced mana to pool
        for mana_type, amount in solution.mana_produced.items():
            if amount > 0:
                pool.add(mana_type, amount)

    def pay_cost(
        self,
        player_id: str,
        cost: ManaCost,
        x_value: int = 0,
        *,
        for_card: Any = None,
    ) -> bool:
        """
        Pay a mana cost, auto-tapping lands if needed.

        For simple cases, this auto-taps. For complex cases,
        the caller should use find_auto_tap_solution and execute_tap_solution.

        ``for_card`` is the card whose cost is being paid; restricted mana in
        the pool is only spent when its predicate matches.
        """
        # First try to pay from existing pool
        pool = self.get_pool(player_id)
        if pool.can_pay(cost, x_value, for_card=for_card):
            return pool.pay(cost, x_value, for_card=for_card)

        # Try auto-tap (auto-tap doesn't know about restrictions; it just
        # adds unrestricted mana to the pool, then we re-attempt to pay).
        success, solution = self.auto_tap_and_pay(player_id, cost, x_value, for_card=for_card)
        if success:
            return True

        # If we got a solution but it's ambiguous, use it anyway (default behavior)
        if solution:
            self._execute_tap_solution(player_id, solution)
            return pool.pay(cost, x_value, for_card=for_card)

        return False

    def produce_mana(
        self,
        player_id: str,
        color: ManaType,
        amount: int = 1,
        snow: bool = False,
        source_id: str = None,
        *,
        restriction: Optional[RestrictionFn] = None,
        restriction_text: str = "",
    ):
        """Add mana to a player's pool.

        When ``restriction`` is set, the produced unit(s) carry that
        spend-restriction predicate (see ``ManaUnit.restriction``).
        """
        pool = self.get_pool(player_id)
        pool.add(
            color, amount, snow, source_id=source_id,
            restriction=restriction, restriction_text=restriction_text,
        )

    def produce_mana_restricted(
        self,
        player_id: str,
        color: ManaType,
        amount: int,
        restriction: RestrictionFn,
        *,
        snow: bool = False,
        source_id: str = None,
        restriction_text: str = "",
    ):
        """Add restricted mana to a player's pool.

        Convenience wrapper around ``produce_mana`` for cards that produce
        "Spend this mana only to ..." mana. Each unit will only be spent on
        a spell for which ``restriction(card_def)`` returns True.
        """
        self.produce_mana(
            player_id, color, amount, snow=snow, source_id=source_id,
            restriction=restriction, restriction_text=restriction_text,
        )

    def empty_pools(self):
        """Empty all mana pools (phase/step transition)."""
        for pool in self.pools.values():
            pool.empty()

    def is_mana_ability(self, ability) -> bool:
        """
        Check if an ability is a mana ability.

        Mana abilities:
        - Don't target
        - Could produce mana
        - Aren't loyalty abilities
        - Resolve immediately (don't use the stack)
        """
        # This would need the ability structure to be defined
        # For now, return False and implement when abilities are defined
        return getattr(ability, 'is_mana_ability', False)


# Convenience functions for card definitions
def parse_cost(cost_string: str) -> ManaCost:
    """Parse a mana cost string."""
    return ManaCost.parse(cost_string)


def color_identity(cost_string: str) -> set[Color]:
    """Get color identity from a mana cost string."""
    return ManaCost.parse(cost_string).colors


# ----------------------------------------------------------------------
# Restriction predicates
# ----------------------------------------------------------------------
#
# Predicates take a "card-like" argument: the in-flight ``GameObject`` (so we
# can read ``.characteristics``) or a ``CardDefinition`` (so we can read
# ``.characteristics`` directly). All accessors below tolerate either.


def _card_chars(card: Any):
    """Return the Characteristics object for ``card``, or None if missing."""
    if card is None:
        return None
    chars = getattr(card, "characteristics", None)
    return chars


def _card_subtypes(card: Any) -> set[str]:
    chars = _card_chars(card)
    if chars is None:
        return set()
    subs = getattr(chars, "subtypes", None) or set()
    return {str(s) for s in subs}


def _card_types(card: Any) -> set:
    chars = _card_chars(card)
    if chars is None:
        return set()
    return set(getattr(chars, "types", None) or set())


def _card_mana_value(card: Any) -> int:
    chars = _card_chars(card)
    if chars is None:
        return 0
    cost_str = getattr(chars, "mana_cost", None)
    if cost_str is None:
        cost_str = getattr(card, "mana_cost", None)
    if not cost_str:
        return 0
    try:
        return int(ManaCost.parse(cost_str).mana_value)
    except Exception:
        return 0


def _card_has_x_in_cost(card: Any) -> bool:
    chars = _card_chars(card)
    if chars is None:
        return False
    cost_str = getattr(chars, "mana_cost", None)
    if cost_str is None:
        cost_str = getattr(card, "mana_cost", None)
    if not cost_str:
        return False
    try:
        return ManaCost.parse(cost_str).x_count > 0
    except Exception:
        return False


def restriction_subtype(*subtypes: str) -> RestrictionFn:
    """Return a predicate that accepts cards with any of the given subtypes.

    Subtypes are compared case-insensitively against the card's printed
    subtypes (``card.characteristics.subtypes``).
    """
    wanted = {s.lower() for s in subtypes}

    def _pred(card: Any) -> bool:
        if card is None:
            return False
        return any(s.lower() in wanted for s in _card_subtypes(card))

    return _pred


def restriction_card_type(*card_types) -> RestrictionFn:
    """Return a predicate that accepts cards with any of the given card types
    (CardType enum values, e.g. CardType.CREATURE)."""
    wanted = set(card_types)

    def _pred(card: Any) -> bool:
        if card is None:
            return False
        return bool(_card_types(card) & wanted)

    return _pred


def restriction_min_mana_value(min_mv: int, include_x: bool = True) -> RestrictionFn:
    """Return a predicate that accepts cards with mana value >= ``min_mv``.

    When ``include_x`` is True (default) cards with ``{X}`` in their cost
    also pass — matching the common "spells with mana value 5+ or with {X}
    in their costs" pattern.
    """
    def _pred(card: Any) -> bool:
        if card is None:
            return False
        mv = _card_mana_value(card)
        if mv >= min_mv:
            return True
        if include_x and _card_has_x_in_cost(card):
            return True
        return False

    return _pred


def restriction_or(*predicates: RestrictionFn) -> RestrictionFn:
    """Combine predicates with OR — passes if any sub-predicate passes."""
    preds = [p for p in predicates if p is not None]

    def _pred(card: Any) -> bool:
        return any(p(card) for p in preds)

    return _pred


def restriction_and(*predicates: RestrictionFn) -> RestrictionFn:
    """Combine predicates with AND — passes only if all sub-predicates pass."""
    preds = [p for p in predicates if p is not None]
    if not preds:
        return lambda _card: True

    def _pred(card: Any) -> bool:
        return all(p(card) for p in preds)

    return _pred


def parse_spend_restriction(text: str) -> Optional[tuple[RestrictionFn, str]]:
    """Try to extract a "Spend this mana only to ..." restriction from rules text.

    Returns ``(predicate, summary)`` on a hit, or ``None`` if no recognised
    spell-cast restriction is found. Activated-ability-only restrictions
    (``Spend this mana only to activate abilities``) intentionally return
    ``None`` — the engine's restricted-mana support is currently scoped to
    spell casting; cards that mix the two are wired with the spell portion
    only and the activated-ability portion is treated as unrestricted.
    """
    if not text:
        return None
    # Find the clause after the trigger phrase, stopping at the next sentence.
    m = re.search(
        r"spend this mana only to\s+(?P<clause>[^.]+)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    clause = m.group("clause").strip().lower()

    preds: list[RestrictionFn] = []
    summary_parts: list[str] = []

    ctype_map = {
        "creature": CardType.CREATURE,
        "instant": CardType.INSTANT,
        "sorcery": CardType.SORCERY,
        "enchantment": CardType.ENCHANTMENT,
        "artifact": CardType.ARTIFACT,
        "land": CardType.LAND,
        "planeswalker": CardType.PLANESWALKER,
    }
    stop = {
        "of", "the", "chosen", "type", "with", "and", "or",
        "a", "an", "this", "that", "from", "exile", "spell", "spells",
        "to", "cast", "card", "cards", "or",
    }

    # Split the clause into "cast ..." segments. We only handle spell-cast
    # restrictions; "or activate abilities of ..." trailers are ignored
    # (treated as no extra restriction beyond the spell side).
    # Strip a trailing "or activate abilities ..." disjunction since that
    # broadens the restriction outside our scope and confuses the parser.
    clause_for_cast = re.sub(
        r"\s*or\s+activate\s+(?:an?\s+)?abilit(?:y|ies)\s+of\s+[^.,]*",
        "",
        clause,
        flags=re.IGNORECASE,
    )
    # Find every "cast X" where X is everything up to the next "or cast",
    # the next sentence/comma, or the end of clause.
    cast_segments = re.findall(
        r"cast\s+([^.]+?)(?=(?:\bor\s+cast\b)|$)",
        clause_for_cast,
        re.IGNORECASE,
    )
    if not cast_segments:
        # Fall back to a single "cast ..." prefix if regex didn't lock on.
        m2 = re.search(r"cast\s+(.+)$", clause_for_cast, re.IGNORECASE)
        if m2:
            cast_segments = [m2.group(1)]

    for seg in cast_segments:
        descriptor = seg.strip()
        # Strip articles and a leading "an?".
        descriptor = re.sub(r"^\s*(?:a|an)\s+", "", descriptor)
        # Mana-value patterns first.
        mv_match = re.search(
            r"with\s+mana\s+value\s+(\d+)\s+or\s+greater",
            descriptor,
        )
        x_in_cost = re.search(
            r"with\s+\{x\}\s+in\s+(?:its|their)\s+mana\s+cost",
            descriptor,
        )
        if mv_match:
            mv = int(mv_match.group(1))
            preds.append(restriction_min_mana_value(mv, include_x=bool(x_in_cost)))
            summary_parts.append(f"MV {mv}+")
            continue
        if x_in_cost and not mv_match:
            # "spells with {X} in their mana costs" — only X-cost spells qualify.
            preds.append(restriction_min_mana_value(10**9, include_x=True))
            summary_parts.append("{X} in cost")
            continue

        # Tokenise the descriptor and split on "or" / "and" disjunctions so
        # alternatives like "Mount or Vehicle" become two subtype options.
        # Replace conjunctions with a sentinel and split.
        normalised = re.sub(r"\s+(or|and)\s+", " | ", descriptor)
        parts = [p.strip() for p in normalised.split("|") if p.strip()]

        seg_subtypes: list[str] = []
        seg_ctypes: list = []
        for part in parts:
            # Trim trailing "spell(s)" / leading articles.
            part = re.sub(r"\b(spell|spells|cards?)\b", "", part)
            part = re.sub(r"^\s*(?:a|an)\s+", "", part).strip()
            tokens = [t for t in re.split(r"\s+", part) if t and t not in stop]
            for tok in tokens:
                # Drop trailing punctuation.
                tok = tok.strip(".,;:")
                if not tok:
                    continue
                if tok in ctype_map:
                    seg_ctypes.append(ctype_map[tok])
                    continue
                # Treat as a subtype name (title-case).
                seg_subtypes.append(tok.title())

        if seg_subtypes:
            preds.append(restriction_subtype(*seg_subtypes))
            summary_parts.append(" or ".join(seg_subtypes) + " spells")
        elif seg_ctypes:
            preds.append(restriction_card_type(*seg_ctypes))
            summary_parts.append(
                " or ".join(t.name.lower() for t in seg_ctypes) + " spells"
            )

    if not preds:
        return None
    combined = preds[0] if len(preds) == 1 else restriction_or(*preds)
    summary = " / ".join(summary_parts) if summary_parts else "restricted"
    return combined, summary
