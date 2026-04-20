"""
Control-change handler.
"""

from ...types import Event, GameState


def _handle_gain_control(event: Event, state: GameState):
    """Handle GAIN_CONTROL event (controller change, usually temporary)."""
    object_id = event.payload.get("object_id")
    new_controller = event.payload.get("new_controller")
    duration = event.payload.get("duration", "end_of_turn")
    if isinstance(duration, str):
        d = duration.strip().lower().replace(" ", "_")
        if d in {"until_end_of_turn", "until_eot", "eot"}:
            duration = "end_of_turn"

    if not object_id or object_id not in state.objects or not new_controller:
        return

    obj = state.objects[object_id]
    if duration == "end_of_turn" and not hasattr(obj.state, "_restore_controller_eot"):
        obj.state._restore_controller_eot = obj.controller

    obj.controller = new_controller

    # Stolen minions can't attack the turn they're taken (summoning sickness)
    obj.state.summoning_sickness = True
