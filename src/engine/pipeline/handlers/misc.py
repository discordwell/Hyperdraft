"""
Handlers that don't cleanly fit other families:
freeze, silence, transform, player-loses.
"""

from ...types import Event, GameState, CardType


def _handle_player_loses(event: Event, state: GameState):
    """Handle PLAYER_LOSES event."""
    player_id = event.payload.get('player')
    if player_id in state.players:
        state.players[player_id].has_lost = True


def _handle_freeze_target(event: Event, state: GameState):
    """Handle FREEZE_TARGET event - freeze a minion or hero."""
    target_id = event.payload.get('target')
    if not target_id or target_id not in state.objects:
        return
    obj = state.objects[target_id]
    obj.state.frozen = True


def _handle_silence_target(event: Event, state: GameState):
    """Handle SILENCE_TARGET event - remove all card text/effects from a minion."""
    target_id = event.payload.get('target')
    if not target_id or target_id not in state.objects:
        return
    obj = state.objects[target_id]

    if CardType.MINION not in obj.characteristics.types:
        return

    # Remove all interceptors registered by this minion
    for int_id in list(obj.interceptor_ids):
        if int_id in state.interceptors:
            del state.interceptors[int_id]
    obj.interceptor_ids.clear()

    # Clear abilities (keywords like Taunt, Divine Shield, etc.)
    obj.characteristics.abilities = []

    # Reset HS-specific state flags
    obj.state.divine_shield = False
    obj.state.stealth = False
    obj.state.windfury = False
    obj.state.frozen = False

    # Reset PT modifications (buffs/debuffs) - revert to base stats
    obj.state.damage = obj.state.damage  # Keep current damage
    if hasattr(obj.state, 'pt_modifiers'):
        obj.state.pt_modifiers = []

    # Clear card_def references so deathrattle/battlecry won't re-fire
    if obj.card_def:
        obj.card_def = type(obj.card_def)(
            name=obj.card_def.name,
            mana_cost=obj.card_def.mana_cost,
            characteristics=obj.card_def.characteristics,
            domain=obj.card_def.domain,
            text="",
            rarity=obj.card_def.rarity,
        )


def _handle_transform(event: Event, state: GameState):
    """
    Handle TRANSFORM event.

    This remains backward-compatible with marker-only TRANSFORM payloads:
    if no transform fields are supplied, it is treated as a no-op marker.
    """
    object_id = event.payload.get('object_id')
    if not object_id or object_id not in state.objects:
        return

    obj = state.objects[object_id]
    payload = event.payload

    new_characteristics = payload.get('new_characteristics') or {}
    changed = False

    # Convenience aliases for simpler card payloads.
    if 'new_name' in payload:
        obj.name = payload.get('new_name') or obj.name
        changed = True
    if 'power' in payload and 'power' not in new_characteristics:
        new_characteristics['power'] = payload.get('power')
    if 'toughness' in payload and 'toughness' not in new_characteristics:
        new_characteristics['toughness'] = payload.get('toughness')
    if 'subtypes' in payload and 'subtypes' not in new_characteristics:
        new_characteristics['subtypes'] = payload.get('subtypes')
    if 'types' in payload and 'types' not in new_characteristics:
        new_characteristics['types'] = payload.get('types')
    if 'abilities' in payload and 'abilities' not in new_characteristics:
        new_characteristics['abilities'] = payload.get('abilities')
    if 'mana_cost' in payload and 'mana_cost' not in new_characteristics:
        new_characteristics['mana_cost'] = payload.get('mana_cost')

    if new_characteristics:
        if 'power' in new_characteristics:
            obj.characteristics.power = new_characteristics.get('power')
        if 'toughness' in new_characteristics:
            obj.characteristics.toughness = new_characteristics.get('toughness')
        if 'subtypes' in new_characteristics:
            obj.characteristics.subtypes = set(new_characteristics.get('subtypes') or set())
        if 'types' in new_characteristics:
            obj.characteristics.types = set(new_characteristics.get('types') or set())
        if 'abilities' in new_characteristics:
            obj.characteristics.abilities = list(new_characteristics.get('abilities') or [])
        if 'mana_cost' in new_characteristics:
            obj.characteristics.mana_cost = new_characteristics.get('mana_cost')
        changed = True

    if payload.get('reset_damage'):
        obj.state.damage = 0
        changed = True
    if 'set_damage' in payload:
        obj.state.damage = int(payload.get('set_damage') or 0)
        changed = True
    if payload.get('reset_counters'):
        obj.state.counters = {}
        changed = True
    if payload.get('reset_pt_modifiers') and hasattr(obj.state, 'pt_modifiers'):
        obj.state.pt_modifiers = []
        changed = True
    if payload.get('reset_state_flags'):
        obj.state.divine_shield = False
        obj.state.stealth = False
        obj.state.windfury = False
        obj.state.frozen = False
        changed = True
    if 'summoning_sickness' in payload:
        obj.state.summoning_sickness = bool(payload.get('summoning_sickness'))
        changed = True

    if payload.get('clear_interceptors'):
        for int_id in list(obj.interceptor_ids):
            if int_id in state.interceptors:
                del state.interceptors[int_id]
        obj.interceptor_ids.clear()
        changed = True

    if payload.get('clear_card_def'):
        obj.card_def = None
        changed = True

    # Marker-only transforms intentionally do nothing else.
    if not changed:
        return
