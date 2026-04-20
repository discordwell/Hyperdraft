"""
Graveyard-scoped handlers: return-from-graveyard (to hand or battlefield)
and grant permissions tied to graveyard play.
"""

from typing import Optional

from ...types import (
    Event, EventType, GameState, ZoneType, CardType, PendingChoice,
)
from .._shared import (
    _set_turn_permission,
    _parse_duration_turns,
)


def _filter_graveyard_cards(
    state: GameState,
    player_id: str,
    *,
    card_type: Optional[CardType] = None,
    max_mana_value: Optional[int] = None,
) -> list[str]:
    gy = state.zones.get(f"graveyard_{player_id}")
    if not gy:
        return []

    out: list[str] = []
    for cid in list(gy.objects):
        obj = state.objects.get(cid)
        if not obj or obj.zone != ZoneType.GRAVEYARD:
            continue
        if card_type and card_type not in obj.characteristics.types:
            continue
        if max_mana_value is not None:
            from ...mana import ManaCost
            mv = ManaCost.parse(obj.characteristics.mana_cost or "").mana_value
            if mv > int(max_mana_value):
                continue
        out.append(cid)
    return out


def _handle_grant_cast_from_graveyard(event: Event, state: GameState):
    """
    Handle GRANT_CAST_FROM_GRAVEYARD.

    Payload (best-effort):
      - player / controller: player_id
      - duration: string ("this_turn", "end_of_turn", "forever", etc.)
      - until_turn: explicit inclusive turn number (optional)
    """
    player_id = event.payload.get("player") or event.payload.get("controller") or event.controller or state.active_player
    if not player_id:
        return

    expires_turn = event.payload.get("until_turn")
    if expires_turn is not None:
        try:
            expires_turn = int(expires_turn)
        except Exception:
            expires_turn = None
    else:
        duration = event.payload.get("duration", "this_turn")
        expires_turn = _parse_duration_turns(duration, state)

    _set_turn_permission(state.cast_from_graveyard_until, player_id, expires_turn)


def _handle_grant_play_lands_from_graveyard(event: Event, state: GameState):
    """
    Handle GRANT_PLAY_LANDS_FROM_GRAVEYARD.

    Payload (best-effort):
      - player / controller: player_id
      - duration / until_turn
    """
    player_id = event.payload.get("player") or event.payload.get("controller") or event.controller or state.active_player
    if not player_id:
        return

    expires_turn = event.payload.get("until_turn")
    if expires_turn is not None:
        try:
            expires_turn = int(expires_turn)
        except Exception:
            expires_turn = None
    else:
        duration = event.payload.get("duration", "this_turn")
        expires_turn = _parse_duration_turns(duration, state)

    _set_turn_permission(state.play_lands_from_graveyard_until, player_id, expires_turn)


def _handle_grant_exile_instead_of_graveyard(event: Event, state: GameState):
    """
    Handle GRANT_EXILE_INSTEAD_OF_GRAVEYARD.

    Payload (best-effort):
      - player / controller: player_id (whose graveyard is replaced)
      - duration / until_turn
    """
    player_id = event.payload.get("player") or event.payload.get("controller") or event.controller or state.active_player
    if not player_id:
        return

    expires_turn = event.payload.get("until_turn")
    if expires_turn is not None:
        try:
            expires_turn = int(expires_turn)
        except Exception:
            expires_turn = None
    else:
        duration = event.payload.get("duration", "this_turn")
        expires_turn = _parse_duration_turns(duration, state)

    _set_turn_permission(state.exile_instead_of_graveyard_until, player_id, expires_turn)


def _handle_return_to_hand_from_graveyard(event: Event, state: GameState):
    """
    Handle RETURN_TO_HAND_FROM_GRAVEYARD.

    Payload (best-effort):
      - player / controller: chooser (defaults to event.controller / state.active_player)
      - object_id: specific card to return (optional)
      - card_type: string ("creature", "land", etc.) (optional)
      - max_mv: int (optional)
      - amount: int (optional, default 1)
    """
    player_id = event.payload.get("player") or event.payload.get("controller") or event.controller or state.active_player
    if not player_id:
        return []

    object_id = event.payload.get("object_id")
    amount = event.payload.get("amount", 1)
    try:
        amount = int(amount)
    except Exception:
        amount = 1
    if amount <= 0:
        return []

    type_token = (event.payload.get("card_type") or event.payload.get("filter") or "").strip().lower()
    type_map = {
        "land": CardType.LAND,
        "creature": CardType.CREATURE,
        "artifact": CardType.ARTIFACT,
        "enchantment": CardType.ENCHANTMENT,
        "planeswalker": CardType.PLANESWALKER,
        "instant": CardType.INSTANT,
        "sorcery": CardType.SORCERY,
    }
    ct = type_map.get(type_token) if type_token else None
    max_mv = event.payload.get("max_mv")
    if max_mv is None:
        max_mv = event.payload.get("max_mana_value")
    if max_mv is not None:
        try:
            max_mv = int(max_mv)
        except Exception:
            max_mv = None

    # Direct return of a specific card.
    if object_id and object_id in state.objects:
        obj = state.objects[object_id]
        if obj.zone == ZoneType.GRAVEYARD:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": object_id,
                    "from_zone": f"graveyard_{obj.owner}",
                    "from_zone_type": ZoneType.GRAVEYARD,
                    "to_zone": f"hand_{obj.owner}",
                    "to_zone_type": ZoneType.HAND,
                },
                source=event.source,
                controller=player_id,
            )]
        return []

    eligible = _filter_graveyard_cards(state, player_id, card_type=ct, max_mana_value=max_mv)
    if len(eligible) < amount:
        return []

    # If there's no choice, execute immediately.
    if len(eligible) == amount:
        out: list[Event] = []
        for cid in eligible:
            obj = state.objects.get(cid)
            if not obj:
                continue
            out.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": cid,
                    "from_zone": f"graveyard_{obj.owner}",
                    "from_zone_type": ZoneType.GRAVEYARD,
                    "to_zone": f"hand_{obj.owner}",
                    "to_zone_type": ZoneType.HAND,
                },
                source=event.source,
                controller=player_id,
            ))
        return out

    def _on_choose(choice: PendingChoice, selected: list, st: GameState) -> list[Event]:
        picked = []
        for s in selected or []:
            if isinstance(s, dict):
                sid = s.get("id") or s.get("target_id")
                if sid is not None:
                    picked.append(str(sid))
            else:
                picked.append(str(s))
        picked = [cid for cid in picked if cid in eligible][:amount]
        out: list[Event] = []
        for cid in picked:
            obj = st.objects.get(cid)
            if not obj or obj.zone != ZoneType.GRAVEYARD:
                continue
            out.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": cid,
                    "from_zone": f"graveyard_{obj.owner}",
                    "to_zone": f"hand_{obj.owner}",
                    "to_zone_type": ZoneType.HAND,
                },
                source=event.source,
                controller=player_id,
            ))
        return out

    state.pending_choice = PendingChoice(
        choice_type="target_with_callback",
        player=player_id,
        prompt=f"Return {amount} card(s) from your graveyard to your hand",
        options=eligible,
        source_id=event.source or "",
        min_choices=amount,
        max_choices=amount,
        callback_data={"handler": _on_choose},
    )
    return []


def _handle_return_from_graveyard(event: Event, state: GameState):
    """
    Handle RETURN_FROM_GRAVEYARD (to battlefield).

    Payload (best-effort):
      - player / controller: chooser (defaults to event.controller / state.active_player)
      - object_id: specific card to return (optional)
      - card_type: string ("creature", etc.) (optional)
      - max_mv: int (optional)
      - amount: int (optional, default 1)
    """
    player_id = event.payload.get("player") or event.payload.get("controller") or event.controller or state.active_player
    if not player_id:
        return []

    # Back-compat: some older card scripts use RETURN_FROM_GRAVEYARD with
    # payload {"to": "hand"} for "return ... to your hand" effects.
    to = event.payload.get("to")
    if isinstance(to, str) and to.strip().lower() in {"hand", "to_hand"}:
        return _handle_return_to_hand_from_graveyard(event, state) or []

    object_id = event.payload.get("object_id")
    amount = event.payload.get("amount", 1)
    try:
        amount = int(amount)
    except Exception:
        amount = 1
    if amount <= 0:
        return []

    type_token = (event.payload.get("card_type") or event.payload.get("filter") or "").strip().lower()
    type_map = {
        "land": CardType.LAND,
        "creature": CardType.CREATURE,
        "artifact": CardType.ARTIFACT,
        "enchantment": CardType.ENCHANTMENT,
        "planeswalker": CardType.PLANESWALKER,
    }
    ct = type_map.get(type_token) if type_token else None
    max_mv = event.payload.get("max_mv")
    if max_mv is None:
        max_mv = event.payload.get("max_mana_value")
    if max_mv is not None:
        try:
            max_mv = int(max_mv)
        except Exception:
            max_mv = None

    if object_id and object_id in state.objects:
        obj = state.objects[object_id]
        if obj.zone == ZoneType.GRAVEYARD:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": object_id,
                    "from_zone": f"graveyard_{obj.owner}",
                    "from_zone_type": ZoneType.GRAVEYARD,
                    "to_zone": "battlefield",
                    "to_zone_type": ZoneType.BATTLEFIELD,
                },
                source=event.source,
                controller=player_id,
            )]
        return []

    eligible = _filter_graveyard_cards(state, player_id, card_type=ct, max_mana_value=max_mv)
    if len(eligible) < amount:
        return []

    if len(eligible) == amount:
        out: list[Event] = []
        for cid in eligible:
            obj = state.objects.get(cid)
            if not obj:
                continue
            out.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": cid,
                    "from_zone": f"graveyard_{obj.owner}",
                    "from_zone_type": ZoneType.GRAVEYARD,
                    "to_zone": "battlefield",
                    "to_zone_type": ZoneType.BATTLEFIELD,
                },
                source=event.source,
                controller=player_id,
            ))
        return out

    def _on_choose(choice: PendingChoice, selected: list, st: GameState) -> list[Event]:
        picked = []
        for s in selected or []:
            if isinstance(s, dict):
                sid = s.get("id") or s.get("target_id")
                if sid is not None:
                    picked.append(str(sid))
            else:
                picked.append(str(s))
        picked = [cid for cid in picked if cid in eligible][:amount]
        out: list[Event] = []
        for cid in picked:
            obj = st.objects.get(cid)
            if not obj or obj.zone != ZoneType.GRAVEYARD:
                continue
            out.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    "object_id": cid,
                    "from_zone": f"graveyard_{obj.owner}",
                    "to_zone": "battlefield",
                    "to_zone_type": ZoneType.BATTLEFIELD,
                },
                source=event.source,
                controller=player_id,
            ))
        return out

    state.pending_choice = PendingChoice(
        choice_type="target_with_callback",
        player=player_id,
        prompt=f"Return {amount} card(s) from your graveyard to the battlefield",
        options=eligible,
        source_id=event.source or "",
        min_choices=amount,
        max_choices=amount,
        callback_data={"handler": _on_choose},
    )
    return []
