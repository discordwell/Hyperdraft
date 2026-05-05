"""
OTJ Crime Mechanic

A player commits a crime when they target an opponent, an opponent's
permanent, or a card in an opponent's graveyard with a spell or ability.

Detection points:
1. ``submit_choice`` -> ``check_targets_for_crime`` after the player picks
   targets for a TARGET_REQUIRED-style PendingChoice.
2. ``priority.cast_spell`` -> ``check_cast_targets_for_crime`` when a spell
   is cast that has pre-chosen targets in its action.

State:
- ``state.turn_data['crimes_<player>']`` is a counter (int). > 0 means the
  player has committed a crime this turn. Cleared on TURN_END alongside the
  rest of ``turn_data``.

Emitted events:
- ``EventType.CRIME_COMMITTED`` with payload
  ``{'player': player_id, 'targets': [target_ids], 'source': source_id}``.
  Cards observe this via ``make_crime_committed_trigger``.
"""

from typing import Iterable, Optional

from .types import Event, EventType, GameState, ZoneType


# =============================================================================
# Public API
# =============================================================================

def is_crime_committed(player: str, state: GameState) -> bool:
    """Has ``player`` committed a crime this turn?"""
    return int(state.turn_data.get(f'crimes_{player}', 0) or 0) > 0


def crime_count(player: str, state: GameState) -> int:
    """Number of crimes ``player`` has committed this turn."""
    return int(state.turn_data.get(f'crimes_{player}', 0) or 0)


def _is_opponent_target(target_id: str, controller_id: str, state: GameState) -> bool:
    """Return True if ``target_id`` is an opponent / opponent's permanent /
    card in an opponent's graveyard.

    target_id may be a player ID or a GameObject ID.
    """
    if target_id is None:
        return False

    # Player target
    if target_id in state.players:
        return target_id != controller_id

    # Object target
    obj = state.objects.get(target_id)
    if obj is None:
        return False

    # An opponent's permanent on the battlefield
    if obj.zone == ZoneType.BATTLEFIELD and obj.controller != controller_id:
        return True

    # A card in an opponent's graveyard
    if obj.zone == ZoneType.GRAVEYARD and obj.owner != controller_id:
        return True

    # Spells on the stack controlled by an opponent are also crimes
    # (countering an opponent's spell, etc.)
    if obj.zone == ZoneType.STACK and obj.controller != controller_id:
        return True

    return False


# Public alias of the opponent-target check (CR 701.55).
def is_crime_target(target_id, actor_player_id: str, state: GameState) -> bool:
    """Return True iff ``target_id`` is an opponent, an opponent's permanent,
    a card in an opponent's graveyard, or an opponent-controlled spell on the
    stack — i.e. targeting it constitutes a crime per CR 701.55.

    ``target_id`` may be a player id, an object id, or a dict with ``id`` /
    ``target_id`` keys (mirrors ``detect_crime``).
    """
    if isinstance(target_id, dict):
        target_id = target_id.get('id') or target_id.get('target_id')
    elif hasattr(target_id, 'id') and not isinstance(target_id, str):
        # Target dataclass (src.engine.targeting.Target)
        target_id = target_id.id
    if not target_id:
        return False
    return _is_opponent_target(str(target_id), actor_player_id, state)


def targets_constitute_crime(
    targets,
    actor_player_id: str,
    state: GameState,
) -> bool:
    """Vectorized check: True iff ``targets`` contains at least one
    opponent / opponent's permanent / opponent's GY card.

    ``targets`` follows the ``PlayerAction.targets`` shape (list of lists)
    OR a flat list of ids — both are accepted.
    """
    for group in (targets or []):
        if isinstance(group, (list, tuple, set)):
            for tid in group:
                if is_crime_target(tid, actor_player_id, state):
                    return True
        else:
            if is_crime_target(group, actor_player_id, state):
                return True
    return False


def detect_crime(
    controller_id: str,
    target_ids: Iterable,
    state: GameState,
    source_id: Optional[str] = None,
) -> list[Event]:
    """Inspect ``target_ids`` for a crime by ``controller_id``. If at least one
    target is an opponent / opp's permanent / opp's GY card, increment the
    crime counter and return a list with a single ``CRIME_COMMITTED`` event.

    Returns an empty list if no crime was committed (or ``controller_id`` is
    falsy).
    """
    if not controller_id:
        return []

    crime_targets: list = []
    for tid in target_ids or []:
        # Normalize Target dataclass / dicts / raw ids to a string id.
        if isinstance(tid, dict):
            tid = tid.get('id') or tid.get('target_id')
        elif hasattr(tid, 'id') and not isinstance(tid, str):
            # Target dataclass (src.engine.targeting.Target)
            tid = tid.id
        if tid and _is_opponent_target(str(tid), controller_id, state):
            crime_targets.append(tid)

    if not crime_targets:
        return []

    key = f'crimes_{controller_id}'
    state.turn_data[key] = int(state.turn_data.get(key, 0) or 0) + 1

    return [Event(
        type=EventType.CRIME_COMMITTED,
        payload={
            'player': controller_id,
            'targets': crime_targets,
            'source': source_id,
        },
        source=source_id,
        controller=controller_id,
    )]


def check_targets_for_crime(choice, selected: list, state: GameState) -> list[Event]:
    """Hook for ``Game._process_choice``. Inspects a resolved
    ``target_with_callback`` (or generic ``target``) PendingChoice and
    returns CRIME_COMMITTED events if a crime was committed.

    The pipeline is responsible for emitting the returned events; this
    function only checks state and returns events to be emitted.
    """
    if not selected:
        return []

    controller_id = (
        choice.callback_data.get('controller_id')
        or choice.callback_data.get('controller')
        or choice.player
    )
    source_id = choice.source_id or choice.callback_data.get('source_id')

    return detect_crime(controller_id, selected, state, source_id)


def check_cast_targets_for_crime(
    controller_id: str,
    targets,
    state: GameState,
    source_id: Optional[str] = None,
) -> list[Event]:
    """Hook for spell casting. ``targets`` follows the ``PlayerAction.targets``
    shape: a list of lists of target IDs (one inner list per requirement).
    """
    flat: list = []
    for group in (targets or []):
        if isinstance(group, (list, tuple, set)):
            flat.extend(group)
        else:
            flat.append(group)
    return detect_crime(controller_id, flat, state, source_id)
