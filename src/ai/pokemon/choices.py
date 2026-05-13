"""
Pokemon AI ``make_choice`` dispatcher.

Called by ``PokemonAIAdapter.make_choice`` (`src/ai/pokemon/adapter.py`)
when the engine raises a ``PendingChoice`` and the resolving player is
AI-controlled. Dispatches by ``choice.choice_type`` and returns the
selection list (e.g. ``[0]`` for "pick mode 0", or ``[target_id]`` for a
target choice).

Phase 1a contract: the dispatch is intentionally simple. Per-card AI
biases live in ``trainers.py`` / Phase 2's ``brv_spice_scorers.py``; this
file just routes the existing card-level ``heuristic_pick`` to the right
slot of the PendingChoice. Phase 2 will extend the modal scorer to
re-evaluate mode effects under the active bias preset.

Choice types handled:

- ``pkm_modal_with_callback``: modal Trainer / attack effect. Mode is an
  index into ``choice.options``. Honors ``callback_data['heuristic_pick']``,
  else picks 0.
- ``pkm_target_choice``: single target from ``choice.options``. Honors
  ``callback_data['heuristic_pick']`` (a target ID OR an index), else
  the first option.

Anything else falls back to ``[0]`` — the same neutral default the stub
provided in the prior pass.
"""

from __future__ import annotations

from typing import Any


def dispatch_choice(player_id: str, choice, state) -> list:
    """Return the AI's selection for ``choice``.

    Always returns a list (the engine's choice contract).
    """
    if choice is None:
        return [0]

    cb = getattr(choice, 'callback_data', None) or {}
    preset = cb.get('heuristic_pick')

    choice_type = getattr(choice, 'choice_type', '')

    if choice_type == 'pkm_modal_with_callback':
        return _resolve_modal(choice, preset)

    if choice_type == 'pkm_target_choice':
        return _resolve_target(choice, preset)

    # Fallback: prefer heuristic_pick, else first option.
    if preset is not None:
        return _wrap(preset)
    options = getattr(choice, 'options', None) or []
    return [0] if options else [0]


def _resolve_modal(choice, preset: Any) -> list:
    """Pick a mode index from ``choice.options``.

    Order of preference:
      1. ``preset`` if provided (the helper's per-card heuristic).
      2. First mode with non-empty text containing common high-value
         keywords ("draw", "search", "discard", "tutor"), if any.
      3. Mode 0.
    """
    if preset is not None:
        idx = preset[0] if isinstance(preset, list) else preset
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = 0
        return [_clamp_idx(idx, choice.options)]

    options = getattr(choice, 'options', None) or []
    if not options:
        return [0]

    HIGH_VALUE = ("draw", "search", "tutor", "discard from your opponent",
                  "discard from opp", "knockout", "switch")
    for i, opt in enumerate(options):
        if not isinstance(opt, dict):
            continue
        text = str(opt.get('text', '')).lower()
        if any(k in text for k in HIGH_VALUE):
            return [i]
    return [0]


def _resolve_target(choice, preset: Any) -> list:
    """Pick a target from ``choice.options``.

    ``preset`` may be a target ID directly or an index. We support both:
    if it's a string and appears in ``choice.options``, return [preset];
    otherwise treat as an index.
    """
    options = getattr(choice, 'options', None) or []
    if preset is not None:
        if isinstance(preset, list) and preset:
            return preset
        if isinstance(preset, str) and preset in options:
            return [preset]
        try:
            idx = int(preset)
            return [_clamp_option(idx, options)]
        except (TypeError, ValueError):
            pass
    if options:
        return [options[0]]
    return [0]


def _clamp_idx(idx: int, options: list) -> int:
    if not options:
        return 0
    if idx < 0:
        return 0
    if idx >= len(options):
        return len(options) - 1
    return idx


def _clamp_option(idx: int, options: list):
    if not options:
        return 0
    if idx < 0:
        return options[0]
    if idx >= len(options):
        return options[-1]
    return options[idx]
