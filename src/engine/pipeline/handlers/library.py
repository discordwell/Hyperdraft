"""
Library-manipulation handlers: SCRY, SURVEIL, EXILE_FROM_TOP (and aliases),
IMPULSE_TO_GRAVEYARD.
"""

from ...types import (
    Event, EventType, GameState, ZoneType, PendingChoice,
)
from .._shared import (
    _remove_object_from_all_zones,
    _exile_instead_of_graveyard_active,
    _parse_duration_turns,
)


def _handle_exile_from_top(event: Event, state: GameState):
    """
    Handle EXILE_FROM_TOP and related impulse-exile events.

    Supported event types (various card scripts):
      - EXILE_FROM_TOP / EXILE_TOP
      - EXILE_TOP_CARD
      - EXILE_TOP_PLAY
      - IMPULSE_DRAW

    Payload (best-effort, keys vary by set):
      - player: player_id whose library to exile from
      - count / amount: number of cards to exile (default 1)
      - may_play: bool (EXILE_TOP_CARD) - whether some player may play the card(s)
      - caster: player_id who may play the exiled card(s) (if may_play)
      - until / duration / playable_until: duration string (optional)
    """
    player_id = event.payload.get("player") or event.controller or state.active_player
    if not player_id or player_id not in state.players:
        return

    amount = event.payload.get("amount")
    count = event.payload.get("count", amount)
    if count is None:
        count = 1
    try:
        count = int(count)
    except Exception:
        count = 1
    if count <= 0:
        return

    library_key = f"library_{player_id}"
    exile_key = "exile"
    library = state.zones.get(library_key)
    exile_zone = state.zones.get(exile_key)
    if not library or not exile_zone:
        return

    # Determine whether the exiled cards are playable from exile.
    may_play = bool(event.payload.get("may_play"))
    if event.type in {EventType.IMPULSE_DRAW, EventType.EXILE_TOP_PLAY}:
        may_play = True

    playable_by = event.payload.get("caster") or event.controller or player_id
    duration = (
        event.payload.get("until")
        or event.payload.get("duration")
        or event.payload.get("playable_until")
    )
    expires_turn = _parse_duration_turns(duration, state)

    to_exile = list(library.objects[:count])
    if not to_exile:
        return

    for obj_id in to_exile:
        if obj_id not in state.objects:
            continue

        # Remove from any zone that currently references it (robust).
        _remove_object_from_all_zones(obj_id, state)

        exile_zone.objects.append(obj_id)
        obj = state.objects[obj_id]
        obj.zone = ZoneType.EXILE
        obj.entered_zone_at = state.timestamp

        if may_play and playable_by:
            obj.state._playable_from_exile_by = playable_by
            if expires_turn is not None:
                obj.state._playable_from_exile_through_turn = expires_turn


def _handle_impulse_to_graveyard(event: Event, state: GameState):
    """
    Handle IMPULSE_TO_GRAVEYARD (look at top N, take some, rest to graveyard).

    Payload (best-effort):
      - player: player_id
      - look: N (default 1)
      - take: M (default 1)
    """
    player_id = event.payload.get("player") or event.controller or state.active_player
    if not player_id or player_id not in state.players:
        return

    look = event.payload.get("look", 1)
    take = event.payload.get("take", 1)
    try:
        look = int(look)
        take = int(take)
    except Exception:
        look = 1
        take = 1

    if look <= 0:
        return
    take = max(0, min(take, look))

    library_key = f"library_{player_id}"
    hand_key = f"hand_{player_id}"
    library = state.zones.get(library_key)
    hand = state.zones.get(hand_key)
    graveyard_key = f"graveyard_{player_id}"
    graveyard = state.zones.get(graveyard_key)
    exile_zone = state.zones.get("exile")
    if not library or not hand or not graveyard or not exile_zone:
        return

    seen = list(library.objects[:look])
    if not seen:
        return

    to_hand = seen[:take]
    to_graveyard = seen[take:]

    for obj_id in to_hand:
        if obj_id not in state.objects:
            continue
        _remove_object_from_all_zones(obj_id, state)
        hand.objects.append(obj_id)
        obj = state.objects[obj_id]
        obj.zone = ZoneType.HAND
        obj.entered_zone_at = state.timestamp

    for obj_id in to_graveyard:
        if obj_id not in state.objects:
            continue
        _remove_object_from_all_zones(obj_id, state)
        if _exile_instead_of_graveyard_active(player_id, state):
            exile_zone.objects.append(obj_id)
            obj = state.objects[obj_id]
            obj.zone = ZoneType.EXILE
        else:
            graveyard.objects.append(obj_id)
            obj = state.objects[obj_id]
            obj.zone = ZoneType.GRAVEYARD
        obj.entered_zone_at = state.timestamp


def _handle_surveil(event: Event, state: GameState):
    """
    Handle SURVEIL event.

    Look at top N cards of library, put any number in graveyard (rest stay on top).

    Payload:
        player: player_id
        amount: N (number of cards to surveil)
        to_graveyard: list of indices (0-indexed) to put in graveyard
                      If not provided, creates a PendingChoice for the player
        source_id: Optional source card ID for the choice
    """
    player_id = event.payload.get('player')
    # Support both 'amount' and legacy 'count' keys.
    amount = event.payload.get('amount') or event.payload.get('count', 1)

    library_key = f"library_{player_id}"
    graveyard_key = f"graveyard_{player_id}"

    if library_key not in state.zones or graveyard_key not in state.zones:
        return

    library = state.zones[library_key]
    graveyard = state.zones[graveyard_key]
    exile_zone = state.zones.get("exile")

    # Get top N cards (without removing yet)
    cards_to_look = library.objects[:amount]

    if not cards_to_look:
        return

    # Check if player selection is provided
    to_graveyard_indices = event.payload.get('to_graveyard')

    if to_graveyard_indices is None:
        # No selection provided - create a choice for the player
        source_id = event.payload.get('source_id', event.source or '')
        choice = PendingChoice(
            choice_type="surveil",
            player=player_id,
            prompt=f"Surveil {amount}: Choose cards to put into your graveyard",
            options=cards_to_look,  # Card IDs being surveiled
            source_id=source_id,
            min_choices=0,
            max_choices=len(cards_to_look),
            callback_data={"surveil_count": amount}
        )
        state.pending_choice = choice
        return  # Don't process yet - wait for player choice

    # Some call sites emit post-resolution SURVEIL summary payloads where
    # to_graveyard is a count, not an index/card-id list. In that case, skip
    # re-processing library order here.
    if isinstance(to_graveyard_indices, int):
        return

    if not isinstance(to_graveyard_indices, (list, tuple, set)):
        return

    # Convert to set for O(1) lookup
    graveyard_set = set(to_graveyard_indices)

    # Process cards - those in graveyard_set go to graveyard, others stay on top
    cards_to_gy = []
    cards_to_keep = []

    for i, card_id in enumerate(cards_to_look):
        # Accept either indices (int) or direct card IDs (str).
        if i in graveyard_set or card_id in graveyard_set:
            cards_to_gy.append(card_id)
        else:
            cards_to_keep.append(card_id)

    # Remove all surveiled cards from library
    for card_id in cards_to_look:
        library.objects.remove(card_id)

    # Put cards back on top (cards_to_keep) - in original order
    library.objects = cards_to_keep + library.objects

    exile_instead = bool(player_id and _exile_instead_of_graveyard_active(player_id, state) and exile_zone)

    # Put cards in graveyard (or exile, if a replacement effect applies).
    for card_id in cards_to_gy:
        if card_id not in state.objects:
            continue
        _remove_object_from_all_zones(card_id, state)
        if exile_instead and exile_zone is not None:
            exile_zone.objects.append(card_id)
            state.objects[card_id].zone = ZoneType.EXILE
        else:
            graveyard.objects.append(card_id)
            state.objects[card_id].zone = ZoneType.GRAVEYARD
        state.objects[card_id].entered_zone_at = state.timestamp


def _handle_scry(event: Event, state: GameState):
    """
    Handle SCRY event.

    Look at top N cards of library, put any number on bottom (rest stay on top).

    Payload:
        player: player_id
        count/amount: N (number of cards to scry) - accepts both keys
        to_bottom: list of indices (0-indexed) to put on bottom
                   If not provided, creates a PendingChoice for the player
        source_id: Optional source card ID for the choice
    """
    player_id = event.payload.get('player')
    # Support both 'count' and 'amount' (many cards use 'amount')
    count = event.payload.get('count') or event.payload.get('amount', 1)

    library_key = f"library_{player_id}"

    if library_key not in state.zones:
        return

    library = state.zones[library_key]

    # Get top N cards (without removing yet)
    cards_to_look = library.objects[:count]

    if not cards_to_look:
        return

    # Check if player selection is provided
    to_bottom_indices = event.payload.get('to_bottom')

    if to_bottom_indices is None:
        # No selection provided - create a choice for the player
        source_id = event.payload.get('source_id', event.source or '')
        choice = PendingChoice(
            choice_type="scry",
            player=player_id,
            prompt=f"Scry {count}: Choose cards to put on the bottom of your library",
            options=cards_to_look,  # Card IDs being scried
            source_id=source_id,
            min_choices=0,
            max_choices=len(cards_to_look),
            callback_data={"scry_count": count}
        )
        state.pending_choice = choice
        return  # Don't process yet - wait for player choice

    # Some call sites emit post-resolution SCRY summary payloads where
    # to_bottom is a count, not an index list. In that case, skip
    # re-processing library order here.
    if isinstance(to_bottom_indices, int):
        return

    if not isinstance(to_bottom_indices, (list, tuple, set)):
        return

    # Convert to set for O(1) lookup
    bottom_set = set(to_bottom_indices)

    # Process cards - those in bottom_set go to bottom, others stay on top
    cards_to_bottom = []
    cards_to_keep = []

    for i, card_id in enumerate(cards_to_look):
        if i in bottom_set:
            cards_to_bottom.append(card_id)
        else:
            cards_to_keep.append(card_id)

    # Remove all scried cards from library
    for card_id in cards_to_look:
        library.objects.remove(card_id)

    # Put cards back on top (cards_to_keep) - in original order
    library.objects = cards_to_keep + library.objects

    # Put cards on bottom
    library.objects.extend(cards_to_bottom)


def _bottom_others_in_random_order(
    others: list[str], library, state: GameState
) -> None:
    """Bottom each card in ``others`` (random order) onto ``library``.

    Removes each card from its current zone first (in case it was placed in
    EXILE during the discover scan) and clears any temporary exile marker.
    """
    import random as _rnd
    _rnd.shuffle(others)
    for cid in others:
        obj = state.objects.get(cid)
        if obj is None:
            continue
        _remove_object_from_all_zones(cid, state)
        library.objects.append(cid)
        obj.zone = ZoneType.LIBRARY
        obj.entered_zone_at = state.timestamp


def _handle_discover(event: Event, state: GameState):
    """
    Handle DISCOVER event.

    Discover N (CR 702.166): Exile cards from the top of your library until
    you exile a nonland card with mana value N or less. The player may cast
    that card without paying its mana cost OR put it into their hand. Then
    put all other cards exiled this way on the bottom of your library in a
    random order.

    Flow:
      1. Exile cards from the top until either the library is empty or a
         non-land card with MV <= N is exiled (the "discover hit").
      2. If a hit was found: prompt the controller with a "may" choice
         (cast-for-free vs put in hand) using the existing PendingChoice
         infrastructure. The callback handles both branches and then bottoms
         the other exiled cards in random order.
      3. If no hit (all cards exceeded N): no choice, just bottom the
         exiled cards in random order.

    Cast-for-free path: builds a PlayerAction with data['_alt_cost']=True
    and routes through priority._handle_cast_spell_sync(). The cast handler
    skips mana payment when this flag is set (see "Discover cast-for-free"
    section in priority.py).

    Payload:
        player: player_id
        value/amount/count: N (mana-value cap)
        source_id (optional): source for the resulting choice
    """
    from ...mana import _card_mana_value
    from ...types import CardType, PendingChoice

    player_id = event.payload.get('player') or event.controller or state.active_player
    if not player_id or player_id not in state.players:
        return
    n = (
        event.payload.get('value')
        or event.payload.get('amount')
        or event.payload.get('count', 0)
    )
    try:
        n = int(n)
    except Exception:
        n = 0
    if n <= 0:
        return

    library_key = f"library_{player_id}"
    hand_key = f"hand_{player_id}"
    library = state.zones.get(library_key)
    hand = state.zones.get(hand_key)
    exile_zone = state.zones.get('exile')
    if library is None or hand is None or exile_zone is None:
        return

    # Step 1: scan from the top of the library, exiling each card we
    # examine. Stop as soon as we exile a non-land with MV <= N.
    others: list[str] = []
    discover_hit: str | None = None
    while library.objects:
        top_id = library.objects.pop(0)
        top = state.objects.get(top_id)
        if top is None:
            continue
        # Move into the exile zone (CR 702.166 says all examined cards are
        # exiled while we're still scanning).
        _remove_object_from_all_zones(top_id, state)
        exile_zone.objects.append(top_id)
        top.zone = ZoneType.EXILE
        top.entered_zone_at = state.timestamp

        types = top.characteristics.types or set()
        if CardType.LAND in types:
            others.append(top_id)
            continue
        mv = _card_mana_value(top)
        if mv <= n:
            discover_hit = top_id
            break
        others.append(top_id)

    if discover_hit is None:
        # Corner case: no eligible non-land found. Bottom everything we
        # exiled in a random order; nothing in hand or cast.
        _bottom_others_in_random_order(others, library, state)
        return

    source_id = event.payload.get('source_id') or event.source or ''

    def _resolve_discover(
        choice: PendingChoice, selected: list, st: GameState
    ) -> list[Event]:
        """Resolve the cast-vs-hand choice, then bottom the others."""
        # Default to "hand" if the AI/auto-resolver picks nothing.
        pick = "hand"
        if selected:
            first = selected[0]
            pick_id = first.get('id') if isinstance(first, dict) else first
            pick = str(pick_id).lower()

        events: list[Event] = []
        hit_obj = st.objects.get(discover_hit)
        if hit_obj is None:
            _bottom_others_in_random_order(others, library, st)
            return events

        cast_succeeded = False
        if pick == "cast":
            # Route the cast through the priority system so target choice,
            # CRIME_COMMITTED, SPELL_CAST, etc. all fire normally. Mana
            # payment is skipped via action.data['_alt_cost'].
            game = getattr(st, '_game', None)
            priority = getattr(game, 'priority_system', None) if game else None
            if priority is not None and hasattr(priority, '_handle_cast_spell_sync'):
                # Lazy imports to avoid circular dependency at module load.
                from ...priority import PlayerAction, ActionType
                # Targets: callers that pre-supply targets via callback_data
                # ("auto_targets") get them honoured; otherwise empty (the
                # cast pipeline / spell builder will surface a TARGET_REQUIRED
                # PendingChoice on resolution if needed).
                pre_targets = choice.callback_data.get('auto_targets') or []
                action = PlayerAction(
                    type=ActionType.CAST_SPELL,
                    player_id=player_id,
                    card_id=discover_hit,
                    targets=pre_targets,
                    x_value=0,
                    data={'_alt_cost': True},
                )
                cast_events = priority._handle_cast_spell_sync(action)
                events.extend(cast_events or [])
                # If the cast produced events (CAST + maybe TARGET_CHOSEN /
                # CRIME_COMMITTED), the card is now on the stack.
                cast_succeeded = bool(cast_events) or hit_obj.zone == ZoneType.STACK

        if not cast_succeeded:
            # Either pick == "hand", or the cast couldn't be initiated
            # (no priority system, etc.). Default to putting it in hand.
            _remove_object_from_all_zones(discover_hit, st)
            hand.objects.append(discover_hit)
            hit_obj.zone = ZoneType.HAND
            hit_obj.entered_zone_at = st.timestamp

        # Bottom the others either way.
        _bottom_others_in_random_order(others, library, st)
        return events

    # Step 2: present the cast-vs-hand choice. Both options are always
    # available (you can always choose to put the card in hand), so this is
    # a single-pick choice rather than a "may".
    hit_obj = state.objects.get(discover_hit)
    hit_name = hit_obj.name if hit_obj else "the discovered card"
    choice = PendingChoice(
        choice_type="discover_cast_or_hand",
        player=player_id,
        prompt=f"Discover: cast {hit_name} without paying its mana cost, or put it into your hand?",
        options=[
            {'id': 'cast', 'label': f"Cast {hit_name} for free"},
            {'id': 'hand', 'label': f"Put {hit_name} into your hand"},
        ],
        source_id=source_id,
        min_choices=1,
        max_choices=1,
        callback_data={
            'handler': _resolve_discover,
            'discover_hit': discover_hit,
            'others': list(others),
            # Tests/cards that already know their target list can pre-supply
            # it here so the cast-for-free branch doesn't stall on a
            # follow-up PendingChoice. Shape: list[list[Target]].
            'auto_targets': event.payload.get('auto_targets') or [],
        },
    )
    state.pending_choice = choice
