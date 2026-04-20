"""
Aggregated event-handler registry.

Each handler module declares a few free functions; this file ties them to the
``EventType`` enum in the single ``EVENT_HANDLERS`` dict that
``EventPipeline._resolve_event`` looks up at dispatch time.

Handler bodies live in per-family modules (damage.py, draw.py, zone.py, ...).
"""

from ...types import EventType

from .damage import (
    _handle_damage,
    _handle_life_change,
    _handle_armor_gain,
    _handle_weapon_equip,
)
from .draw import (
    _handle_draw,
    _handle_add_to_hand,
    _handle_mill,
    _handle_discard,
)
from .zone import (
    _handle_object_created,
    _handle_zone_change,
    _handle_tap,
    _handle_untap,
    _handle_object_destroyed,
    _handle_sacrifice,
    _handle_create_token,
    _handle_exile,
    _handle_return_to_hand,
)
from .counters import (
    _handle_counter_added,
    _handle_counter_removed,
)
from .pt import (
    _handle_pt_modification,
    _handle_pt_change,  # alias; exported for back-compat
    _handle_grant_keyword,
)
from .control import _handle_gain_control
from .graveyard import (
    _handle_grant_cast_from_graveyard,
    _handle_grant_play_lands_from_graveyard,
    _handle_grant_exile_instead_of_graveyard,
    _handle_return_to_hand_from_graveyard,
    _handle_return_from_graveyard,
)
from .library import (
    _handle_exile_from_top,
    _handle_impulse_to_graveyard,
    _handle_surveil,
    _handle_scry,
)
from .mana import _handle_mana_produced
from .targeting import _handle_target_required
from .misc import (
    _handle_player_loses,
    _handle_freeze_target,
    _handle_silence_target,
    _handle_transform,
)


EVENT_HANDLERS = {
    EventType.DAMAGE: _handle_damage,
    EventType.LIFE_CHANGE: _handle_life_change,
    EventType.DRAW: _handle_draw,
    EventType.OBJECT_CREATED: _handle_object_created,
    EventType.ZONE_CHANGE: _handle_zone_change,
    EventType.TAP: _handle_tap,
    EventType.UNTAP: _handle_untap,
    EventType.GAIN_CONTROL: _handle_gain_control,
    EventType.CONTROL_CHANGE: _handle_gain_control,
    EventType.COUNTER_ADDED: _handle_counter_added,
    EventType.COUNTER_REMOVED: _handle_counter_removed,
    # All P/T-modifier event types route to the single unified handler,
    # which normalizes both payload shapes (power_mod/toughness_mod vs
    # power/toughness, duration vs until).
    EventType.PT_MODIFICATION: _handle_pt_modification,
    EventType.PT_MODIFIER: _handle_pt_modification,
    EventType.PT_CHANGE: _handle_pt_modification,
    EventType.PT_MODIFY: _handle_pt_modification,
    EventType.TEMPORARY_PT_CHANGE: _handle_pt_modification,
    EventType.PUMP: _handle_pt_modification,
    EventType.TEMPORARY_BOOST: _handle_pt_modification,
    EventType.GRANT_PT_MODIFIER: _handle_pt_modification,
    EventType.GRANT_KEYWORD: _handle_grant_keyword,
    EventType.KEYWORD_GRANT: _handle_grant_keyword,
    EventType.GRANT_ABILITY: _handle_grant_keyword,
    EventType.GRANT_CAST_FROM_GRAVEYARD: _handle_grant_cast_from_graveyard,
    EventType.GRANT_PLAY_LANDS_FROM_GRAVEYARD: _handle_grant_play_lands_from_graveyard,
    EventType.GRANT_EXILE_INSTEAD_OF_GRAVEYARD: _handle_grant_exile_instead_of_graveyard,
    EventType.RETURN_TO_HAND_FROM_GRAVEYARD: _handle_return_to_hand_from_graveyard,
    EventType.RETURN_FROM_GRAVEYARD: _handle_return_from_graveyard,
    EventType.OBJECT_DESTROYED: _handle_object_destroyed,
    EventType.SACRIFICE: _handle_sacrifice,
    EventType.MANA_PRODUCED: _handle_mana_produced,
    EventType.PLAYER_LOSES: _handle_player_loses,
    EventType.CREATE_TOKEN: _handle_create_token,
    EventType.EXILE: _handle_exile,
    EventType.EXILE_FROM_TOP: _handle_exile_from_top,
    EventType.EXILE_TOP: _handle_exile_from_top,
    EventType.EXILE_TOP_CARD: _handle_exile_from_top,
    EventType.EXILE_TOP_PLAY: _handle_exile_from_top,
    EventType.IMPULSE_DRAW: _handle_exile_from_top,
    EventType.IMPULSE_TO_GRAVEYARD: _handle_impulse_to_graveyard,
    EventType.SURVEIL: _handle_surveil,
    EventType.SCRY: _handle_scry,
    EventType.MILL: _handle_mill,
    EventType.DISCARD: _handle_discard,
    EventType.TARGET_REQUIRED: _handle_target_required,
    EventType.FREEZE_TARGET: _handle_freeze_target,
    EventType.SILENCE_TARGET: _handle_silence_target,
    EventType.TRANSFORM: _handle_transform,
    EventType.ADD_TO_HAND: _handle_add_to_hand,
    EventType.RETURN_TO_HAND: _handle_return_to_hand,
    EventType.BOUNCE: _handle_return_to_hand,
    EventType.ARMOR_GAIN: _handle_armor_gain,
    EventType.WEAPON_EQUIP: _handle_weapon_equip,
}


__all__ = ["EVENT_HANDLERS"]
