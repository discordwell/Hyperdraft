"""
Hyperdraft Mana System

Handles mana costs, mana pools, and mana payment.
Supports standard MTG mana syntax: {W}, {U}, {B}, {R}, {G}, {C}, {X}, {1}, {2}, etc.
Also supports hybrid {W/U}, Phyrexian {W/P}, and snow {S}.
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto

from .types import Color, GameState


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
    """A single unit of mana in a pool."""
    color: ManaType
    snow: bool = False
    restrictions: list[str] = field(default_factory=list)  # e.g., ["creature spells only"]
    source_id: Optional[str] = None


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
        source_id: str = None
    ):
        """Add mana to the pool."""
        for _ in range(amount):
            self.mana.append(ManaUnit(
                color=color,
                snow=snow,
                restrictions=restrictions or [],
                source_id=source_id
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

    def can_pay(self, cost: ManaCost, x_value: int = 0) -> bool:
        """
        Check if the pool can pay a mana cost.

        Uses a greedy algorithm that tries to pay specific costs first,
        then generic with remaining mana.
        """
        return self._try_pay(cost, x_value, actually_pay=False)

    def pay(self, cost: ManaCost, x_value: int = 0) -> bool:
        """
        Actually pay a mana cost, removing mana from pool.
        Returns True if successful, False if unable to pay.
        """
        return self._try_pay(cost, x_value, actually_pay=True)

    def _try_pay(self, cost: ManaCost, x_value: int, actually_pay: bool) -> bool:
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
        """
        # Work with a copy if not actually paying
        available = list(self.mana) if not actually_pay else self.mana

        def remove_mana(color: ManaType, count: int, snow_required: bool = False) -> bool:
            """Remove specified mana from available pool."""
            removed = 0
            to_remove = []

            for i, unit in enumerate(available):
                if removed >= count:
                    break
                if unit.color == color:
                    if snow_required and not unit.snow:
                        continue
                    to_remove.append(i)
                    removed += 1

            if removed < count:
                return False

            # Remove in reverse order to maintain indices
            for i in reversed(to_remove):
                available.pop(i)
            return True

        def remove_any(count: int, snow_required: bool = False) -> bool:
            """Remove any mana from pool."""
            removed = 0
            to_remove = []

            for i, unit in enumerate(available):
                if removed >= count:
                    break
                if snow_required and not unit.snow:
                    continue
                to_remove.append(i)
                removed += 1

            if removed < count:
                return False

            for i in reversed(to_remove):
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


class ManaSystem:
    """
    High-level mana system that integrates with the game.
    """

    def __init__(self, game_state: GameState):
        self.state = game_state
        self.pools: dict[str, ManaPool] = {}  # player_id -> ManaPool

    def get_pool(self, player_id: str) -> ManaPool:
        """Get or create a player's mana pool."""
        if player_id not in self.pools:
            self.pools[player_id] = ManaPool()
        return self.pools[player_id]

    def can_cast(self, player_id: str, cost: ManaCost, x_value: int = 0) -> bool:
        """Check if a player can pay a mana cost."""
        pool = self.get_pool(player_id)
        return pool.can_pay(cost, x_value)

    def pay_cost(self, player_id: str, cost: ManaCost, x_value: int = 0) -> bool:
        """Pay a mana cost from a player's pool."""
        pool = self.get_pool(player_id)
        return pool.pay(cost, x_value)

    def produce_mana(
        self,
        player_id: str,
        color: ManaType,
        amount: int = 1,
        snow: bool = False,
        source_id: str = None
    ):
        """Add mana to a player's pool."""
        pool = self.get_pool(player_id)
        pool.add(color, amount, snow, source_id=source_id)

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
