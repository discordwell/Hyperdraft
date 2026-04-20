"""
Card-movement handlers that operate on libraries/hands/graveyards:
DRAW, MILL, ADD_TO_HAND, DISCARD.
"""

from typing import Optional

from ...types import Event, GameState, ZoneType, CardType
from .._shared import (
    _remove_object_from_all_zones,
    _exile_instead_of_graveyard_active,
)


def _handle_draw(event: Event, state: GameState):
    """Handle DRAW event."""
    from ...mode_adapter import get_mode_adapter
    adapter = get_mode_adapter(state.game_mode)

    player_id = event.payload.get('player')
    # Support both 'amount' (used by most cards) and 'count' (legacy)
    # Use 'is not None' to avoid treating 0 as falsy
    count = event.payload.get('amount')
    if count is None:
        count = event.payload.get('count', 1)
    if count <= 0:
        return

    # Find player's library and hand
    library_key = f"library_{player_id}"
    hand_key = f"hand_{player_id}"

    if library_key not in state.zones or hand_key not in state.zones:
        return

    library = state.zones[library_key]
    hand = state.zones[hand_key]
    fatigue_events = []

    for _ in range(count):
        if not library.objects:
            player = state.players.get(player_id)
            if player is None:
                break
            # Adapter handles empty-library draw (fatigue for HS, lose-game for MTG/YGO).
            follow_ups = adapter.handle_empty_library_draw(player, state)
            if follow_ups:
                fatigue_events.extend(follow_ups)
                continue  # Each remaining draw triggers separate fatigue
            break

        # Check hand size limit (modes that enforce mid-turn burn, e.g. HS).
        player = state.players.get(player_id)
        hand_limit = adapter.hand_size_limit(player, state) if player else None
        if (hand_limit is not None
                and adapter.overdraw_burns(state)
                and len(hand.objects) >= hand_limit):
            # Overdraw - burn the card
            card_id = library.objects.pop(0)
            graveyard_key = f"graveyard_{player_id}"
            if graveyard_key in state.zones:
                _remove_object_from_all_zones(card_id, state)
                state.zones[graveyard_key].objects.append(card_id)
                if card_id in state.objects:
                    state.objects[card_id].zone = ZoneType.GRAVEYARD
                    state.objects[card_id].entered_zone_at = state.timestamp
            continue

        card_id = library.objects.pop(0)  # Top of library
        # Be robust against zone corruption: ensure the card isn't referenced in
        # any other zone list before we put it into the hand.
        _remove_object_from_all_zones(card_id, state)
        hand.objects.append(card_id)

        if card_id in state.objects:
            state.objects[card_id].zone = ZoneType.HAND
            state.objects[card_id].entered_zone_at = state.timestamp

    # Return fatigue damage events so the pipeline processes them
    if fatigue_events:
        return fatigue_events


def _handle_add_to_hand(event: Event, state: GameState):
    """
    Handle ADD_TO_HAND event.

    Creates a new GameObject from a card definition and places it in the player's hand.

    Payload:
        player: Player ID who receives the card
        card_def: dict with card characteristics (name, mana_cost, types, power, toughness, etc.)
                  OR a CardDefinition object
    """
    from ...types import new_id, GameObject, Characteristics, ObjectState

    player_id = event.payload.get('player')
    card_def = event.payload.get('card_def')

    if not player_id or not card_def or player_id not in state.players:
        return

    hand_key = f"hand_{player_id}"
    if hand_key not in state.zones:
        return

    hand = state.zones[hand_key]

    # Respect mid-turn hand limit (HS: 10 cards; MTG: none).
    from ...mode_adapter import get_mode_adapter
    adapter = get_mode_adapter(state.game_mode)
    player = state.players.get(player_id)
    hand_limit = adapter.hand_size_limit(player, state) if player else None
    if hand_limit is not None and len(hand.objects) >= hand_limit:
        return

    # If card_def is a CardDefinition object, create GameObject from it
    if hasattr(card_def, 'characteristics'):
        obj_id = new_id()
        obj = GameObject(
            id=obj_id,
            name=card_def.name,
            owner=player_id,
            controller=player_id,
            zone=ZoneType.HAND,
            characteristics=Characteristics(
                types=set(card_def.characteristics.types),
                subtypes=set(card_def.characteristics.subtypes) if card_def.characteristics.subtypes else set(),
                colors=set(card_def.characteristics.colors) if card_def.characteristics.colors else set(),
                power=card_def.characteristics.power,
                toughness=card_def.characteristics.toughness,
                mana_cost=card_def.characteristics.mana_cost or card_def.mana_cost,
                abilities=list(card_def.characteristics.abilities) if card_def.characteristics.abilities else [],
            ),
            state=ObjectState(),
            card_def=card_def,
            entered_zone_at=state.timestamp,
            _state_ref=state,
        )
        if hasattr(card_def, 'text'):
            obj.characteristics.text = card_def.text
    else:
        # card_def is a dict
        obj_id = new_id()
        types = card_def.get('types', {CardType.SPELL})
        if isinstance(types, list):
            types = set(types)

        obj = GameObject(
            id=obj_id,
            name=card_def.get('name', 'Unknown'),
            owner=player_id,
            controller=player_id,
            zone=ZoneType.HAND,
            characteristics=Characteristics(
                types=types,
                mana_cost=card_def.get('mana_cost', '{0}'),
                power=card_def.get('power'),
                toughness=card_def.get('toughness'),
            ),
            state=ObjectState(),
            entered_zone_at=state.timestamp,
            _state_ref=state,
        )

    state.objects[obj_id] = obj
    hand.objects.append(obj_id)


def _handle_mill(event: Event, state: GameState):
    """
    Handle MILL event.

    Move top N cards from library directly to graveyard.

    Payload:
        player: player_id
        count/amount: N (number of cards to mill) - accepts both keys
    """
    player_id = event.payload.get('player')
    # Support both 'count' and 'amount' (many cards use 'amount')
    count = event.payload.get('count') or event.payload.get('amount', 1)

    library_key = f"library_{player_id}"
    graveyard_key = f"graveyard_{player_id}"

    if library_key not in state.zones:
        return

    library = state.zones[library_key]

    exile_instead = bool(player_id and _exile_instead_of_graveyard_active(player_id, state))
    if exile_instead:
        dest_zone = state.zones.get("exile")
        dest_type = ZoneType.EXILE
    else:
        dest_zone = state.zones.get(graveyard_key)
        dest_type = ZoneType.GRAVEYARD

    if not dest_zone:
        return

    for _ in range(count):
        if not library.objects:
            break

        card_id = library.objects.pop(0)  # Top of library
        _remove_object_from_all_zones(card_id, state)
        dest_zone.objects.append(card_id)

        if card_id in state.objects:
            state.objects[card_id].zone = dest_type
            state.objects[card_id].entered_zone_at = state.timestamp


def _handle_discard(event: Event, state: GameState):
    """
    Handle DISCARD event.

    Moves card(s) from hand to graveyard.

    Payload:
        object_id: str - specific card to discard
        OR
        player: str + amount: int - player discards N cards (requires choice)
    """
    player_id = event.payload.get('player')
    object_id = event.payload.get('object_id')

    if object_id:
        # Discard a specific card
        if object_id not in state.objects:
            return

        obj = state.objects[object_id]
        # Only discard from a hand zone. (Some effects can discard cards a player
        # doesn't own, so don't assume `hand_{obj.owner}`.)
        discarding_player: Optional[str] = event.payload.get("player") or event.controller
        in_hand = False
        for z in state.zones.values():
            if z.type == ZoneType.HAND and object_id in z.objects:
                in_hand = True
                # Zone owner is the player whose hand this is.
                discarding_player = discarding_player or z.owner
                break

        if not in_hand:
            return

        # Discarded cards go to their owner's graveyard unless a replacement
        # effect exiles them instead.
        if _exile_instead_of_graveyard_active(obj.owner, state):
            dest_key = "exile"
            dest_type = ZoneType.EXILE
        else:
            dest_key = f"graveyard_{obj.owner}"
            dest_type = ZoneType.GRAVEYARD

        if dest_key not in state.zones:
            return

        dest = state.zones[dest_key]

        _remove_object_from_all_zones(object_id, state)
        dest.objects.append(object_id)
        obj.zone = dest_type
        obj.entered_zone_at = state.timestamp
        # Remember who discarded it and when (for "discarded this turn" mechanics).
        obj.state.last_discarded_turn = state.turn_number
        obj.state.last_discarded_by = discarding_player
