"""
P/T modification + keyword grant handlers.
"""

from ...types import Event, EventType, GameState


def _handle_pt_modification(event: Event, state: GameState):
    """
    Handle temporary P/T change events.

    Unified handler for the full family of P/T-modifier event types:
      PT_MODIFICATION, PT_MODIFIER, PT_CHANGE, PT_MODIFY,
      TEMPORARY_PT_CHANGE, PUMP, TEMPORARY_BOOST, GRANT_PT_MODIFIER.

    Accepts either payload shape:
      - ``power_mod`` / ``toughness_mod`` (canonical, used by PT_MODIFICATION)
      - ``power`` / ``toughness`` (legacy, used by PT_CHANGE/PUMP/GRANT_PT_MODIFIER)

    Duration may be given as either ``duration`` (canonical) or ``until``
    (legacy). Strings like ``until_end_of_turn`` / ``eot`` are normalized to
    ``end_of_turn``. Modifiers with duration ``end_of_turn`` are swept at the
    cleanup step.

    Stores the modification on the object's state for QUERY handlers to use.
    """
    object_id = event.payload.get('object_id')
    # Accept both canonical and legacy payload keys.
    power_mod = event.payload.get('power_mod', event.payload.get('power', 0))
    toughness_mod = event.payload.get(
        'toughness_mod', event.payload.get('toughness', 0)
    )
    duration = event.payload.get(
        'duration', event.payload.get('until', 'end_of_turn')
    )
    if isinstance(duration, str):
        d = duration.strip().lower().replace(" ", "_")
        if d in {"until_end_of_turn", "until_eot", "eot"}:
            duration = "end_of_turn"

    if object_id not in state.objects:
        return

    obj = state.objects[object_id]

    # Initialize temporary modifiers list if not present
    if not hasattr(obj.state, 'pt_modifiers'):
        obj.state.pt_modifiers = []

    # Add the modifier
    obj.state.pt_modifiers.append({
        'power': power_mod,
        'toughness': toughness_mod,
        'duration': duration,
        'timestamp': state.timestamp
    })


# Backward-compatible alias; _handle_pt_change used to be a separate function
# with a legacy payload shape. It now just delegates to the unified handler so
# any lingering direct references keep working.
_handle_pt_change = _handle_pt_modification


def _handle_grant_keyword(event: Event, state: GameState):
    """
    Handle keyword/ability grants that older card files express as events.

    Supported event types:
      - GRANT_KEYWORD / KEYWORD_GRANT: payload {object_id, keyword, duration}
      - GRANT_ABILITY: payload {object_id, abilities=[...], duration}
    """
    object_id = event.payload.get("object_id")
    if not object_id or object_id not in state.objects:
        return

    obj = state.objects[object_id]

    duration = event.payload.get("duration", "end_of_turn")
    if isinstance(duration, str):
        d = duration.strip().lower().replace(" ", "_")
        if d in {"until_end_of_turn", "until_eot", "eot"}:
            duration = "end_of_turn"

    keywords: list[str] = []
    if event.type == EventType.GRANT_ABILITY:
        abilities = event.payload.get("abilities") or []
        if isinstance(abilities, str):
            abilities = [abilities]
        if isinstance(abilities, (list, tuple, set)):
            keywords = [str(a).strip().lower() for a in abilities if str(a).strip()]
    else:
        kw = event.payload.get("keyword")
        if kw:
            keywords = [str(kw).strip().lower()]

    if not keywords:
        return

    for kw in keywords:
        obj.characteristics.abilities.append({
            "keyword": kw,
            "_temporary": True,
            "_duration": duration,
        })
        # Mirror key Hearthstone keyword flags that are checked by direct state.
        if kw == "divine_shield":
            obj.state.divine_shield = True
        elif kw == "stealth":
            obj.state.stealth = True
        elif kw == "windfury":
            obj.state.windfury = True
        elif kw == "frozen":
            obj.state.frozen = True
