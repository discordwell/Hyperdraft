"""
Hearthstone Mana System

Crystal-based mana system for Hearthstone mode:
- Players gain 1 mana crystal per turn (max 10)
- Mana crystals auto-refill at turn start
- No lands or complex color requirements
"""

from .types import GameState, Player


class HearthstoneManaSystem:
    """
    Hearthstone-style mana system using auto-incrementing crystals.

    Key differences from MTG:
    - No lands - mana crystals auto-gain each turn
    - Single unified mana pool (no colors)
    - Refills completely at turn start
    - Maximum 10 crystals
    """

    def __init__(self, game_state: GameState):
        self.state = game_state

    def on_turn_start(self, player_id: str):
        """
        Gain 1 mana crystal (max 10) and refill available crystals.
        Called at the beginning of each player's turn.
        """
        player = self.state.players.get(player_id)
        if not player:
            return

        # Gain 1 crystal (max 10)
        if player.mana_crystals < 10:
            player.mana_crystals += 1

        # Refill available crystals to max
        player.mana_crystals_available = player.mana_crystals

    def can_pay_cost(self, player_id: str, cost: int) -> bool:
        """
        Check if player has enough available mana crystals to pay cost.

        Args:
            player_id: Player to check
            cost: Mana cost (simple integer)

        Returns:
            True if player has enough crystals, False otherwise
        """
        player = self.state.players.get(player_id)
        if not player:
            return False

        return player.mana_crystals_available >= cost

    def pay_cost(self, player_id: str, cost: int) -> bool:
        """
        Pay a mana cost, deducting crystals from available pool.

        Args:
            player_id: Player paying the cost
            cost: Mana cost (simple integer)

        Returns:
            True if payment successful, False if insufficient mana
        """
        if not self.can_pay_cost(player_id, cost):
            return False

        player = self.state.players[player_id]
        player.mana_crystals_available -= cost
        return True

    def get_available_mana(self, player_id: str) -> int:
        """
        Get the amount of mana currently available to spend.

        Args:
            player_id: Player to check

        Returns:
            Number of available mana crystals
        """
        player = self.state.players.get(player_id)
        if not player:
            return 0
        return player.mana_crystals_available

    def get_max_mana(self, player_id: str) -> int:
        """
        Get the maximum mana crystals for this player.

        Args:
            player_id: Player to check

        Returns:
            Total mana crystals (0-10)
        """
        player = self.state.players.get(player_id)
        if not player:
            return 0
        return player.mana_crystals

    def add_temporary_crystal(self, player_id: str):
        """
        Add a temporary mana crystal this turn only (like "Coin" card).
        Does not increase max crystals, just available for this turn.
        """
        player = self.state.players.get(player_id)
        if player:
            player.mana_crystals_available += 1

    def add_empty_crystal(self, player_id: str, count: int = 1):
        """
        Add empty mana crystal(s) - increases max but not available this turn.
        Used by cards like "Wild Growth".
        """
        player = self.state.players.get(player_id)
        if not player:
            return

        player.mana_crystals = min(10, player.mana_crystals + count)

    def refill_crystals(self, player_id: str):
        """
        Refill available crystals to maximum.
        Normally called at turn start, but some effects may refresh mana mid-turn.
        """
        player = self.state.players.get(player_id)
        if player:
            player.mana_crystals_available = player.mana_crystals

    # MTG compatibility methods (no-ops for Hearthstone mode)

    def get_pool(self, player_id: str):
        """MTG compatibility - returns None in Hearthstone mode."""
        return None

    def get_untapped_lands(self, player_id: str) -> list:
        """MTG compatibility - returns empty list in Hearthstone mode."""
        return []
