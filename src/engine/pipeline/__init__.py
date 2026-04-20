"""
Hyperdraft Event Pipeline

The heart of the engine. Events flow through interceptors:
1. TRANSFORM - modify the event
2. PREVENT - cancel the event
3. RESOLVE - actually do it
4. REACT - trigger responses

The ~3k-line monolithic ``pipeline.py`` was split into this package:

- ``core`` — ``EventPipeline`` class + phase pipeline
- ``_shared`` — helpers shared across handler modules
  (zone removal, turn-permission helpers, keyword-counter bookkeeping,
  ``_exile_instead_of_graveyard_active``)
- ``handlers/`` — one module per event family, aggregated through
  ``handlers/__init__.py`` into the single ``EVENT_HANDLERS`` dict.

External imports should continue to work unchanged:

    from src.engine.pipeline import EventPipeline
    from src.engine.pipeline import EVENT_HANDLERS
"""

from .core import EventPipeline
from .handlers import EVENT_HANDLERS

__all__ = ["EventPipeline", "EVENT_HANDLERS"]
