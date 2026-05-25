"""Engine-agnostic helpers for resolving ``PendingChoice`` inline.

Two functions:

- ``resolve_pending_choice_inline(state)`` — synchronously resolves
  ``state.pending_choice`` IF the choice player is AI. For human players
  it returns immediately with the choice still set on ``state``, so the
  session-level pause-resume in ``src/server/session.py:_get_human_action``
  blocks on the next ``human_action_handler`` invocation.

- ``create_choice_and_resolve(state, ...)`` — one-stop helper for card
  ``effect_fn``s: build a ``PendingChoice``, stash it on ``state``, and
  immediately try to resolve it. Returns the events the chosen mode emitted
  (empty for humans, where the choice stays pending).

This module supersedes the Pokemon-specific
``src/cards/pokemon/_helpers.py:_resolve_pending_choice_inline``, which is
preserved as a compat alias that simply delegates here.

The key behavioral difference from the old Pokemon helper: humans are no
longer silently auto-resolved to option ``[0]``. Today no human ever played
through that path (Pokemon BRV cards only fire mid-AI-turn), but the bug
would have surfaced as soon as a human cast a modal trainer.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from src.engine.types import Event, GameState, PendingChoice


# Per-engine AI handler attribute names on ``game.turn_manager``. Probed in
# order; the first that exists wins. Finance is special — handlers are
# stored per-player in a dict (``finance_ai_handlers[player_id]``).
_AI_HANDLER_ATTRS: tuple[str, ...] = (
    "pokemon_ai_handler",
    "hearthstone_ai_handler",
    "ygo_ai_handler",
    "scp_ai_handler",
    "minecraft_ai_handler",
)


def _lookup_ai_handler(turn_mgr, player_id: str):
    """Find the AI handler for ``player_id`` on ``turn_mgr``.

    Returns the handler instance with a ``make_choice(player_id, choice, state)``
    method, or ``None`` if no engine-specific handler is registered.
    """
    if turn_mgr is None:
        return None
    for attr in _AI_HANDLER_ATTRS:
        handler = getattr(turn_mgr, attr, None)
        if handler is not None:
            return handler
    handlers = getattr(turn_mgr, "finance_ai_handlers", None)
    if isinstance(handlers, dict):
        return handlers.get(player_id)
    return None


def resolve_pending_choice_inline(state: GameState) -> tuple[list[Event], list]:
    """Synchronously resolve ``state.pending_choice`` for an AI player.

    Returns ``(events, selected)``. For human players, returns ``([], [])``
    and leaves ``state.pending_choice`` set so the next call into
    ``session._get_human_action`` blocks on it.

    For AI players: invokes the engine's registered AI handler's
    ``make_choice``; falls back to ``callback_data['heuristic_pick']`` then
    to ``[0]``. Routes the selection through ``Game._process_choice`` so the
    callback_data handler (or built-in type dispatcher) runs. Always clears
    ``state.pending_choice`` on the AI path, even on handler errors, so the
    engine never deadlocks.
    """
    choice = state.pending_choice
    if choice is None:
        return [], []

    game = getattr(state, "_game", None)
    turn_mgr = getattr(game, "turn_manager", None) if game is not None else None
    ai_players = set(getattr(turn_mgr, "ai_players", set()) or set())
    # MTG fallback: per-engine AI players live on ``priority_system.ai_players``
    # rather than ``turn_manager.ai_players``. Without this fallback, an MTG
    # card that calls ``create_choice_and_resolve`` for its AI controller
    # would silently park on the human branch.
    priority_sys = getattr(game, "priority_system", None) if game is not None else None
    if priority_sys is not None:
        ai_players |= set(getattr(priority_sys, "ai_players", set()) or set())

    if choice.player not in ai_players:
        # Human path. Session will block on this choice via _get_human_action.
        return [], []

    try:
        selected: list = []
        ai_handler = _lookup_ai_handler(turn_mgr, choice.player)
        if ai_handler is not None and hasattr(ai_handler, "make_choice"):
            try:
                selected = ai_handler.make_choice(choice.player, choice, state) or []
            except Exception:
                selected = []
        if not selected:
            preset = (choice.callback_data or {}).get("heuristic_pick")
            if preset is None:
                selected = [0]
            elif isinstance(preset, list):
                selected = preset
            else:
                selected = [preset]

        events: list[Event] = []
        if game is not None:
            try:
                events = game._process_choice(choice, selected) or []
            except Exception:
                events = []
        else:
            # Bare test path with no Game wiring. Honor the handler directly.
            handler = (choice.callback_data or {}).get("handler")
            if handler:
                try:
                    events = handler(choice, selected, state) or []
                except Exception:
                    events = []
        return events, selected
    finally:
        state.pending_choice = None


def drain_pending_choices_for_ai(state: GameState, max_iterations: int = 16) -> list[Event]:
    """Drain any pending AI choices on ``state`` and return aggregated events.

    Safety net for engine AI adapters: call after a sequence of actions to
    ensure no AI-owned ``PendingChoice`` is left orphaned. A correctly
    written card uses ``create_choice_and_resolve``, which resolves inline,
    so this is usually a no-op. It exists for defense-in-depth.

    For human-owned choices, this function is a no-op (the choice stays
    pending so the session blocks on it).

    ``max_iterations`` guards against pathological loops where a choice's
    resolver immediately emits another choice. 16 is conservative; raise if
    a legitimate engine starts chaining choices.
    """
    events: list[Event] = []
    for _ in range(max_iterations):
        choice = state.pending_choice
        if choice is None:
            break
        game = getattr(state, "_game", None)
        turn_mgr = getattr(game, "turn_manager", None) if game is not None else None
        ai_players = set(getattr(turn_mgr, "ai_players", set()) or set())
        # See ``resolve_pending_choice_inline`` for why we also consult the
        # priority system's AI roster (MTG keeps AI membership there).
        priority_sys = getattr(game, "priority_system", None) if game is not None else None
        if priority_sys is not None:
            ai_players |= set(getattr(priority_sys, "ai_players", set()) or set())
        if choice.player not in ai_players:
            break
        more_events, _ = resolve_pending_choice_inline(state)
        events.extend(more_events)
    return events


def create_x_value_choice(
    state: GameState,
    *,
    player_id: str,
    prompt: str,
    source_id: str,
    min_x: int = 0,
    max_x: int = 99,
    default_x: Optional[int] = None,
    handler: Optional[Callable] = None,
    heuristic_pick: Any = None,
    **extra_callback_data: Any,
) -> list[Event]:
    """Arc D1 — emit a PendingChoice asking the player for an X value.

    Convention: `choice_type='x_value'`. `min_choices` and `max_choices`
    encode the X bounds (so the existing serialization/UI pipeline
    carries them through without schema changes). The submission shape
    is a one-element list containing the chosen integer:
    `submit_choice(['7'])` for X=7.

    The frontend's ChoiceModal renders a number input bounded by
    [min_x, max_x] with `default_x` as the initial value. After
    submission, `handler(choice, selected_x, state)` runs — typical
    pattern: store X on the spell object via callback_data and continue
    to the target-pick phase.

    Engine-agnostic: any game with X-cost or "name a number" style
    choices uses this helper.
    """
    callback_data: dict[str, Any] = dict(extra_callback_data)
    if handler is not None:
        callback_data["handler"] = handler
    if heuristic_pick is not None:
        callback_data["heuristic_pick"] = heuristic_pick
    if default_x is not None:
        callback_data["default_x"] = default_x

    choice = PendingChoice(
        choice_type="x_value",
        player=player_id,
        prompt=prompt,
        options=[],  # No discrete options — frontend renders a number input
        source_id=source_id,
        min_choices=int(min_x),
        max_choices=int(max_x),
        callback_data=callback_data,
        # No target_metadata — x_value is its own choice_type. Frontend
        # branches on choice_type to render the number input.
    )
    state.pending_choice = choice
    events, _selected = resolve_pending_choice_inline(state)
    return events


def create_choice_and_resolve(
    state: GameState,
    *,
    choice_type: str,
    player_id: str,
    prompt: str,
    options: list,
    source_id: str,
    min_choices: int = 1,
    max_choices: int = 1,
    handler: Optional[Callable] = None,
    heuristic_pick: Any = None,
    target_metadata: Any = None,  # Optional[TargetGroupMetadata] — Arc B.
    **extra_callback_data: Any,
) -> list[Event]:
    """Build a ``PendingChoice``, stash on ``state``, resolve if AI.

    For humans, returns ``[]`` and leaves the choice pending. The session
    layer (``src/server/session.py:1034``) will block on it the next time
    the human's action handler is called.

    For AI players, invokes the engine's AI handler synchronously via
    ``resolve_pending_choice_inline`` and returns the events the handler
    emitted (typically destroy/draw/damage events that the calling
    ``effect_fn`` should include in its return list).

    Card migration callers MUST short-circuit on empty options BEFORE
    calling this helper. A ``PendingChoice`` with zero options and
    ``min_choices >= 1`` is unsatisfiable and will deadlock the engine
    (the human session will time out after 300s, then the AI fallback
    of ``[0]`` will be out-of-range).
    """
    callback_data: dict[str, Any] = dict(extra_callback_data)
    if handler is not None:
        callback_data["handler"] = handler
    if heuristic_pick is not None:
        callback_data["heuristic_pick"] = heuristic_pick

    choice = PendingChoice(
        choice_type=choice_type,
        player=player_id,
        prompt=prompt,
        options=list(options),
        source_id=source_id,
        min_choices=min_choices,
        max_choices=max_choices,
        callback_data=callback_data,
        target_metadata=target_metadata,
    )
    state.pending_choice = choice
    events, _selected = resolve_pending_choice_inline(state)
    return events
