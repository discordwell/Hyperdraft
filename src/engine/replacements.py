"""
Hyperdraft Replacement Effects Framework
========================================

Replacement effects rewrite events as they pass through the pipeline.
They sit *between* event emission and event resolution: a TRANSFORM-priority
interceptor mutates the event payload (or substitutes the event), and the
mutated event is what the resolver actually applies.

This module provides:

* :func:`make_replacement_interceptor` - generic factory used by every
  ``make_*_replacer`` helper.
* High-level helpers wired to common payloads:
    - :func:`make_life_gain_replacer` ("If you would gain life, ... instead")
    - :func:`make_life_gain_prevention` ("Your opponents can't gain life.")
    - :func:`make_draw_replacer` ("If you would draw a card, draw two instead.")
    - :func:`make_counter_doubler` ("Double counters placed on permanents you
      control.")
    - :func:`make_dies_to_exile_replacer` ("If a creature would die, exile it
      instead.")
    - :func:`make_damage_doubler` ("If a source you control would deal
      damage, it deals double instead.")
    - :func:`make_skip_to_graveyard_replacer` ("If this would be put in a
      graveyard, shuffle it into its owner's library instead.")
    - :func:`make_graveyard_to_exile_replacer` ("Cards going to graveyards from
      anywhere are exiled instead." — narrowed to a card-type filter for
      Dryad Militant style effects.)

Design notes
------------
* All helpers return :class:`~src.engine.types.Interceptor` instances using
  ``InterceptorPriority.TRANSFORM`` so the dispatcher's existing TRANSFORM
  phase rewrites the payload before the resolver runs.
* Helpers gate themselves on ``source_obj.zone == ZoneType.BATTLEFIELD``.
  The dispatcher already drops ``while_on_battlefield`` interceptors when the
  source leaves play, but several effects want to fire on the *very same
  zone-change event* that takes the source off the battlefield (e.g. a
  Doubling Season's "would put counters" reaction is about an unrelated
  permanent), so we keep the explicit guard.
* Counter doubling and damage doubling apply *after* other modifiers because
  ``InterceptorPriority.TRANSFORM`` interceptors are sorted by timestamp and
  a permanent printed with "double" usually wants to multiply the result of
  any pre-existing mods. (For order-sensitive cases we accept "double after
  later effects" as a known limitation; pure additive effects compose
  cleanly.)

Anti-loop
---------
We use a small payload marker, ``_replaced_by``, that the helpers set on the
transformed event. A given replacer will refuse to fire on an event it
already touched, which prevents trivial self-loops like "double counters"
firing on its own output. We *do* still let *other* replacers fire on the
output, so two independent doublers stack to 4x as expected.
"""

from typing import Callable, Optional

from .types import (
    Event,
    EventType,
    GameObject,
    GameState,
    Interceptor,
    InterceptorAction,
    InterceptorPriority,
    InterceptorResult,
    ZoneType,
    new_id,
    CardType,
)


# ---------------------------------------------------------------------------
# Anti-loop marker
# ---------------------------------------------------------------------------

REPLACED_KEY = "_replaced_by"


def _has_been_replaced_by(event: Event, replacer_id: str) -> bool:
    """Return True if ``replacer_id`` already rewrote this event."""
    seen = event.payload.get(REPLACED_KEY)
    if not seen:
        return False
    if isinstance(seen, (list, set, tuple)):
        return replacer_id in seen
    return seen == replacer_id


def _mark_replaced(event: Event, replacer_id: str) -> None:
    """Mark ``event`` as having been touched by ``replacer_id``."""
    seen = event.payload.get(REPLACED_KEY)
    if not seen:
        event.payload[REPLACED_KEY] = [replacer_id]
        return
    if isinstance(seen, list):
        if replacer_id not in seen:
            seen.append(replacer_id)
    elif isinstance(seen, (set, tuple)):
        merged = list(seen)
        if replacer_id not in merged:
            merged.append(replacer_id)
        event.payload[REPLACED_KEY] = merged
    else:
        event.payload[REPLACED_KEY] = [seen, replacer_id]


# ---------------------------------------------------------------------------
# Generic factory
# ---------------------------------------------------------------------------

def make_replacement_interceptor(
    source_obj: GameObject,
    event_filter: Callable[[Event, GameState], bool],
    transform: Callable[[Event, GameState], Optional[Event]],
    *,
    duration: str = "while_on_battlefield",
    require_battlefield: bool = True,
) -> Interceptor:
    """Build a TRANSFORM-priority interceptor implementing a replacement effect.

    Args:
        source_obj: the permanent that supplies the effect.
        event_filter: ``(event, state) -> bool``. If True, the transform runs.
            The factory automatically guards against firing on events this
            same interceptor has already rewritten.
        transform: ``(event, state) -> Optional[Event]``. Return a fresh
            ``Event`` (typically ``event.copy()`` with mutated payload) to
            replace the original. Return ``None`` to fall through.
        duration: standard interceptor duration ('while_on_battlefield' is
            cleaned up automatically when the source leaves play).
        require_battlefield: gate on the source still being on the
            battlefield. Almost always desirable.
    """
    source_id = source_obj.id
    interceptor_id = new_id()

    def filter_fn(event: Event, state: GameState) -> bool:
        if _has_been_replaced_by(event, interceptor_id):
            return False
        if require_battlefield:
            src = state.objects.get(source_id)
            if not src or src.zone != ZoneType.BATTLEFIELD:
                return False
        try:
            return bool(event_filter(event, state))
        except Exception:
            return False

    def handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = transform(event, state)
        if new_event is None:
            return InterceptorResult(action=InterceptorAction.PASS)
        _mark_replaced(new_event, interceptor_id)
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event,
        )

    return Interceptor(
        id=interceptor_id,
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM,
        filter=filter_fn,
        handler=handler,
        duration=duration,
    )


# ---------------------------------------------------------------------------
# LIFE GAIN
# ---------------------------------------------------------------------------

def _life_change_player(event: Event) -> Optional[str]:
    """Pull the affected player ID from a LIFE_CHANGE payload."""
    return (
        event.payload.get("player")
        or event.payload.get("controller")
        or event.controller
    )


def make_life_gain_replacer(
    source_obj: GameObject,
    *,
    multiplier: int = 1,
    addend: int = 0,
    affects_controller: bool = True,
    affects_opponents: bool = False,
) -> Interceptor:
    """Rewrite LIFE_CHANGE events that gain life.

    Examples:
        Angel of Vitality: ``multiplier=1, addend=1``.
        Alhammarret's Archive (life): ``multiplier=2``.
        "Your opponents can't gain life" can be expressed via
        :func:`make_life_gain_prevention`.
    """
    affected_controller = source_obj.controller

    def event_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.LIFE_CHANGE, EventType.LIFE_GAIN):
            return False
        amount = event.payload.get("amount", 0)
        if amount <= 0:
            return False
        target_player = _life_change_player(event)
        if not target_player:
            return False
        if affects_controller and target_player == affected_controller:
            return True
        if affects_opponents and target_player != affected_controller:
            return True
        return False

    def transform(event: Event, state: GameState) -> Optional[Event]:
        amount = event.payload.get("amount", 0)
        new_amount = amount * multiplier + addend
        if new_amount == amount:
            return None
        new_event = event.copy()
        new_event.payload["amount"] = max(0, new_amount)
        return new_event

    return make_replacement_interceptor(source_obj, event_filter, transform)


def make_life_gain_prevention(
    source_obj: GameObject,
    *,
    affects_controller: bool = False,
    affects_opponents: bool = True,
) -> Interceptor:
    """Set life gain to zero (e.g. Giant Cindermaw, Erebos, Rampaging Ferocidon).

    Implemented as a TRANSFORM that zeroes the amount, not a PREVENT, so other
    REACT-priority "if you would gain life" hooks still see a (now-zero)
    LIFE_CHANGE and can decide for themselves.
    """
    return make_life_gain_replacer(
        source_obj,
        multiplier=0,
        addend=0,
        affects_controller=affects_controller,
        affects_opponents=affects_opponents,
    )


# ---------------------------------------------------------------------------
# DRAW
# ---------------------------------------------------------------------------

def make_draw_replacer(
    source_obj: GameObject,
    *,
    multiplier: int = 1,
    addend: int = 0,
    affects_controller: bool = True,
    affects_opponents: bool = False,
) -> Interceptor:
    """Rewrite DRAW events.

    Alhammarret's Archive (cards): ``multiplier=2``.
    Library of Alexandria-style restrictions are PREVENT effects, not these.
    """
    affected_controller = source_obj.controller

    def event_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        # Both 'amount' and 'count' are accepted by the DRAW handler. We pick
        # whichever is set so we leave the other path alone.
        amount = event.payload.get("amount")
        if amount is None:
            amount = event.payload.get("count", 1)
        if amount <= 0:
            return False
        player = event.payload.get("player")
        if not player:
            return False
        if affects_controller and player == affected_controller:
            return True
        if affects_opponents and player != affected_controller:
            return True
        return False

    def transform(event: Event, state: GameState) -> Optional[Event]:
        # Read whichever key is set; write back to the same key.
        if event.payload.get("amount") is not None:
            key = "amount"
        else:
            key = "count"
        amount = event.payload.get(key, 1)
        new_amount = amount * multiplier + addend
        if new_amount == amount:
            return None
        new_event = event.copy()
        new_event.payload[key] = max(0, new_amount)
        return new_event

    return make_replacement_interceptor(source_obj, event_filter, transform)


# ---------------------------------------------------------------------------
# COUNTERS
# ---------------------------------------------------------------------------

def make_counter_doubler(
    source_obj: GameObject,
    *,
    counter_type: Optional[str] = None,
    multiplier: int = 2,
    addend: int = 0,
    affects_player: Optional[str] = None,
    target_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
) -> Interceptor:
    """Double (or otherwise scale) counters as they're placed.

    Doubling Season is the canonical example: ``counter_type=None`` meaning
    "all counters", ``affects_player`` defaulting to source's controller via
    ``target_filter``.

    Args:
        counter_type: only fire on this counter type ('+1/+1', 'loyalty',
            'time', etc.). ``None`` matches every counter.
        multiplier/addend: amount becomes ``amount * multiplier + addend``.
        affects_player: only fire when the target permanent is controlled by
            this player ID. Defaults to ``source_obj.controller`` if neither
            ``affects_player`` nor ``target_filter`` is provided. Pass an
            empty string ``""`` to match any player.
        target_filter: full predicate ``(target_obj, state) -> bool``.
            Overrides ``affects_player`` if both are given.
    """
    src_controller = source_obj.controller

    def event_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        amount = event.payload.get("amount", 1)
        if amount <= 0:
            return False
        if counter_type is not None:
            ev_ctype = event.payload.get("counter_type", "+1/+1")
            if ev_ctype != counter_type:
                return False
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id)
        if not target:
            return False
        if target_filter is not None:
            return bool(target_filter(target, state))
        # Default: only the controller's own permanents.
        affected = affects_player if affects_player is not None else src_controller
        if affected == "":  # Sentinel: any player.
            return True
        return target.controller == affected

    def transform(event: Event, state: GameState) -> Optional[Event]:
        amount = event.payload.get("amount", 1)
        new_amount = amount * multiplier + addend
        if new_amount == amount:
            return None
        new_event = event.copy()
        new_event.payload["amount"] = max(0, new_amount)
        return new_event

    return make_replacement_interceptor(source_obj, event_filter, transform)


# ---------------------------------------------------------------------------
# DEATH -> EXILE
# ---------------------------------------------------------------------------

def make_dies_to_exile_replacer(
    source_obj: GameObject,
    *,
    target_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
    self_only: bool = False,
) -> Interceptor:
    """Replace OBJECT_DESTROYED with EXILE for matching creatures.

    Implementation uses the existing ``_exile_on_leave_battlefield`` flag on
    ``ObjectState`` so the destroy handler routes the corpse to the exile
    zone. We set the flag in the TRANSFORM phase and let the original event
    proceed; this preserves source/payload fields that other interceptors
    might read.

    Args:
        target_filter: predicate ``(target_obj, state) -> bool`` selecting
            which dying objects get exiled. Defaults to "any creature" when
            ``self_only`` is False.
        self_only: only redirect the source's own death (rare; see
            "If this dies, exile it instead").
    """
    source_id = source_obj.id

    def event_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.OBJECT_DESTROYED, EventType.SACRIFICE):
            return False
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id)
        if not target:
            return False
        if self_only:
            return target_id == source_id
        if target_filter is not None:
            return bool(target_filter(target, state))
        return CardType.CREATURE in target.characteristics.types

    def transform(event: Event, state: GameState) -> Optional[Event]:
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id)
        if target is None:
            return None
        # The destroy handler in zone.py already honors this flag.
        target.state._exile_on_leave_battlefield = True  # type: ignore[attr-defined]
        # Flip the event payload too so logging is honest about destination.
        new_event = event.copy()
        new_event.payload["redirected_to_exile"] = True
        return new_event

    return make_replacement_interceptor(source_obj, event_filter, transform)


# ---------------------------------------------------------------------------
# DAMAGE doubling
# ---------------------------------------------------------------------------

def make_damage_doubler(
    source_obj: GameObject,
    *,
    multiplier: int = 2,
    affects_controller: bool = True,
    source_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
    target_filter: Optional[Callable[[Optional[GameObject], Optional[str], GameState], bool]] = None,
) -> Interceptor:
    """Double (or otherwise scale) DAMAGE events.

    Examples:
        Gratuitous Violence: source is a creature you control.
        Furnace of Rath: every source.
        Twinflame Tyrant: damage from your sources to opponents/their
            permanents -> double.

    Args:
        multiplier: damage scaling.
        affects_controller: when True (default) and ``source_filter`` is None,
            we only fire when the damage source is controlled by
            ``source_obj.controller``.
        source_filter: ``(source_object, state) -> bool``. When set, replaces
            the controller check.
        target_filter: ``(target_obj, target_player_id, state) -> bool``.
            ``target_obj`` is None when damage targets a player, and
            ``target_player_id`` is None when damage targets an object.
    """
    src_controller = source_obj.controller

    def event_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        amount = event.payload.get("amount", 0)
        if amount <= 0:
            return False
        # Source check.
        damage_source_id = event.source or event.payload.get("source")
        damage_source = state.objects.get(damage_source_id) if damage_source_id else None
        if source_filter is not None:
            if not source_filter(damage_source, state):
                return False
        elif affects_controller:
            if not damage_source or damage_source.controller != src_controller:
                return False
        # Target check.
        if target_filter is not None:
            target_id = event.payload.get("target")
            target_obj = state.objects.get(target_id) if target_id else None
            target_player = target_id if target_id in state.players else None
            if not target_filter(target_obj, target_player, state):
                return False
        return True

    def transform(event: Event, state: GameState) -> Optional[Event]:
        amount = event.payload.get("amount", 0)
        new_amount = amount * multiplier
        if new_amount == amount:
            return None
        new_event = event.copy()
        new_event.payload["amount"] = max(0, new_amount)
        return new_event

    return make_replacement_interceptor(source_obj, event_filter, transform)


# ---------------------------------------------------------------------------
# GRAVEYARD redirection
# ---------------------------------------------------------------------------

def make_skip_to_graveyard_replacer(
    source_obj: GameObject,
    *,
    redirect_to: ZoneType = ZoneType.LIBRARY,
    self_only: bool = True,
    target_filter: Optional[Callable[[GameObject, GameState], bool]] = None,
    shuffle_after: bool = True,
) -> Interceptor:
    """Replace OBJECT_DESTROYED -> graveyard with a different zone.

    Default behaviour matches Progenitus and Darksteel Colossus: when the
    source itself would die, shuffle it into its owner's library instead.

    Args:
        redirect_to: where the object should end up. Currently only LIBRARY
            (shuffle) and EXILE are honoured by helper handling; for other
            zones we fall back to PREVENT semantics (the destroy is cancelled
            and the caller is responsible for the alternate destination).
        self_only / target_filter: see :func:`make_dies_to_exile_replacer`.
        shuffle_after: when ``redirect_to == LIBRARY``, shuffle the library
            after insertion.
    """
    source_id = source_obj.id

    def event_filter(event: Event, state: GameState) -> bool:
        if event.type not in (EventType.OBJECT_DESTROYED, EventType.SACRIFICE):
            return False
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id)
        if not target:
            return False
        if self_only:
            return target_id == source_id
        if target_filter is not None:
            return bool(target_filter(target, state))
        return True

    def transform(event: Event, state: GameState) -> Optional[Event]:
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id)
        if target is None:
            return None

        if redirect_to == ZoneType.EXILE:
            target.state._exile_on_leave_battlefield = True  # type: ignore[attr-defined]
            new_event = event.copy()
            new_event.payload["redirected_to_exile"] = True
            return new_event

        if redirect_to == ZoneType.LIBRARY:
            # Move directly into the owner's library; cancel the destroy by
            # zeroing-out the payload object_id so the destroy handler skips.
            owner = target.owner
            from .pipeline._shared import _remove_object_from_all_zones

            _remove_object_from_all_zones(target_id, state)
            library_key = f"library_{owner}"
            if library_key in state.zones:
                state.zones[library_key].objects.append(target_id)
                target.zone = ZoneType.LIBRARY
                target.entered_zone_at = state.timestamp
                if shuffle_after:
                    import random

                    random.shuffle(state.zones[library_key].objects)
            new_event = event.copy()
            new_event.payload["redirected_to_library"] = True
            new_event.payload["object_id"] = None  # destroy handler will no-op
            return new_event

        # Fallback: just mark and let the caller handle the rest.
        new_event = event.copy()
        new_event.payload[f"redirected_to_{redirect_to.name.lower()}"] = True
        return new_event

    return make_replacement_interceptor(source_obj, event_filter, transform)


def make_graveyard_to_exile_replacer(
    source_obj: GameObject,
    *,
    card_type_filter: Optional[set] = None,
    affects_controller: bool = True,
    affects_opponents: bool = True,
) -> Interceptor:
    """Cards going to the graveyard are exiled instead.

    Used by Dryad Militant (instants/sorceries) and Rest in Peace-style
    effects.

    Args:
        card_type_filter: set of :class:`CardType` values; only cards with at
            least one matching type are redirected.
        affects_controller / affects_opponents: which players' graveyards are
            affected.
    """
    src_controller = source_obj.controller

    def event_filter(event: Event, state: GameState) -> bool:
        # We rewrite ZONE_CHANGE -> graveyard to ZONE_CHANGE -> exile.
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get("to_zone_type") != ZoneType.GRAVEYARD:
            return False
        target_id = event.payload.get("object_id")
        target = state.objects.get(target_id)
        if not target:
            return False
        owner = target.owner
        if owner == src_controller and not affects_controller:
            return False
        if owner != src_controller and not affects_opponents:
            return False
        if card_type_filter is not None:
            if not (target.characteristics.types & set(card_type_filter)):
                return False
        return True

    def transform(event: Event, state: GameState) -> Optional[Event]:
        new_event = event.copy()
        new_event.payload["to_zone_type"] = ZoneType.EXILE
        # The zone handler reads to_zone_key for keyed zone moves; default
        # exile is the shared 'exile' zone.
        new_event.payload["to_zone_key"] = "exile"
        new_event.payload["redirected_to_exile"] = True
        return new_event

    return make_replacement_interceptor(source_obj, event_filter, transform)


__all__ = [
    "make_replacement_interceptor",
    "make_life_gain_replacer",
    "make_life_gain_prevention",
    "make_draw_replacer",
    "make_counter_doubler",
    "make_dies_to_exile_replacer",
    "make_damage_doubler",
    "make_skip_to_graveyard_replacer",
    "make_graveyard_to_exile_replacer",
    "REPLACED_KEY",
]
