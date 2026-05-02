# STUB-W2: replaced at integration by W1
"""
Heuristic deckbuilder package.

Pure-Python, deterministic deck construction primitives:

* ``score_card(card_def, archetype, colors) -> float`` — lower is better,
  +inf for uncastable cards. (W1)
* ``ARCHETYPE_TEMPLATES`` — ``dict[str, ArchetypeTemplate]`` keyed by
  archetype name ("Aggro", "Midrange", "Control", "Tempo", "Ramp"). (W1)
* ``ArchetypeTemplate`` — dataclass shape used by W2's slot-filling builder. (W1)
* ``resolve_pool(set_codes) -> dict[str, CardDefinition]`` — union the
  card registries for the requested set codes. (W1)
* ``build_heuristic_deck(name, archetype, colors, set_codes, *, seed)`` —
  end-to-end heuristic deck assembly. (W2)
* ``pick_lands(colors, land_count, pool, *, pip_weights, seed)`` —
  archetype-aware mana base picker. (W2)

W2 (slot-filler + manabase) and W3 (LLM polish layer) consume these.

This ``__init__`` also re-exports a few internal helpers (``role_of``,
``cmc_of``, ``is_castable``, ``AGGRO`` etc.) that W1's stub provides — they
will continue to be exported by W1's real implementation.
"""

from .archetypes import (
    ARCHETYPE_TEMPLATES,
    ArchetypeTemplate,
    AGGRO,
    MIDRANGE,
    CONTROL,
    TEMPO,
    RAMP,
    get_template,
)
from .builder import build_heuristic_deck
from .manabase import pick_lands
from .pool import resolve_pool
from .scorer import score_card, role_of, cmc_of, is_castable

__all__ = [
    "score_card",
    "role_of",
    "cmc_of",
    "is_castable",
    "ARCHETYPE_TEMPLATES",
    "ArchetypeTemplate",
    "AGGRO",
    "MIDRANGE",
    "CONTROL",
    "TEMPO",
    "RAMP",
    "get_template",
    "resolve_pool",
    "build_heuristic_deck",
    "pick_lands",
]
