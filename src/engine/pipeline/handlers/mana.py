"""
Mana-related handlers.
"""

from ...types import Event, GameState, Color


def _handle_mana_produced(event: Event, state: GameState):
    """Handle MANA_PRODUCED event."""
    player_id = event.payload.get('player')
    color = event.payload.get('color', Color.COLORLESS)
    amount = event.payload.get('amount', 1)

    if player_id in state.players:
        player = state.players[player_id]
        current = player.mana_pool.get(color, 0)
        player.mana_pool[color] = current + amount
