---
name: implement-mtg-cards
description: "Use when implementing, wiring, testing, or debugging Magic: The Gathering-style cards in Hyperdraft, especially card definitions, setup_interceptors, event/interceptor helpers, targeting, set mechanics, and card tests."
metadata:
  short-description: Implement Hyperdraft MTG cards
---

# Implement MTG Cards

## Operating Model

Hyperdraft's MTG engine is event-driven: everything is an `Event`, and everything else is an `Interceptor`.

Pipeline:

```text
Event -> TRANSFORM -> PREVENT -> RESOLVE -> REACT
```

Continuous/static effects usually answer `QUERY_*` events rather than mutating base characteristics. Triggered abilities use `REACT` interceptors and normally emit follow-up events instead of directly editing state.

## First Reads

Before wiring a card, inspect the current code rather than relying on memory:

- Target set file: `src/cards/<set_name>.py` or `src/cards/custom/<set_name>.py`
- Shared helper surface: `src/cards/interceptor_helpers.py`
- Event and object contracts: `src/engine/types.py`
- Handler behavior for non-obvious payloads: `src/engine/pipeline/handlers/`
- Existing tests for similar cards: `tests/test_*`

Read `references/card-implementation-reference.md` when you need helper examples, canonical payload keys, target handling, set-mechanic notes, or testing patterns.

## Workflow

1. Classify the printed card text: static keyword, triggered ability, activated ability, replacement/prevention, spell resolve effect, or unsupported engine gap.
2. Prefer existing helpers over custom interceptors. If helper signatures are unclear, inspect the helper source.
3. Implement the smallest faithful behavior. If full fidelity needs missing engine support, wire a tested approximation only when that is useful and document the limitation near the code.
4. Register the setup function on the card definition with `setup_interceptors=...` or use a spell `resolve=...` function for instants/sorceries.
5. Add or update focused tests: load shape, positive path, and at least one edge case.
6. If this work uncovers a real engine/helper/test bug, fix that bug before continuing to the next card.
7. Run the narrow test first, then the relevant broader suite when the change touches shared helpers or event contracts.

## Core Patterns

Setup functions return interceptors:

```python
def card_name_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={"player": obj.controller, "amount": 3},
            source=obj.id,
        )]

    return [make_etb_trigger(obj, effect_fn)]
```

Use helper filters for common static effects:

```python
def elf_lord_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_static_pt_boost(
        obj,
        1,
        1,
        other_creatures_with_subtype(obj, "Elf"),
    )
```

For self-keywords not already in characteristics, wire them explicitly:

```python
def flying_self_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_keyword_grant(obj, ["flying"], lambda target, state: target.id == obj.id)]
```

## Spell Resolution

Instants and sorceries without permanent-based triggers should usually use `resolve=` helpers or a local resolve function instead of `setup_interceptors`.

Be defensive with targets in custom resolve functions. Some engine paths pass a nested target list:

```python
def resolve(targets, state):
    if not targets:
        return []
    target = targets[0]
    if isinstance(target, list):
        target = target[0] if target else None
    if target is None:
        return []
    target_id = target if isinstance(target, str) else getattr(target, "object_id", getattr(target, "id", None))
    if target_id is None:
        return []
    return [Event(type=EventType.DAMAGE, payload={"target": target_id, "amount": 3})]
```

## Testing Contract

Mirror existing focused tests. When testing ETB/setup behavior, create in hand with no `card_def`, assign `card_def`, then emit a `ZONE_CHANGE` into battlefield so setup runs once:

```python
obj = game.create_object(
    name=card_name,
    owner_id=player.id,
    zone=ZoneType.HAND,
    characteristics=card_def.characteristics,
    card_def=None,
)
obj.card_def = card_def
game.emit(Event(
    type=EventType.ZONE_CHANGE,
    payload={
        "object_id": obj.id,
        "from_zone": f"hand_{player.id}",
        "to_zone": "battlefield",
        "to_zone_type": ZoneType.BATTLEFIELD,
    },
))
```

Use edge cases that prove the filters are correct: opponent events, self-vs-other, wrong subtype, empty library, wrong phase/active player, or illegal activated ability preconditions.

## Verification

Use the smallest meaningful command first:

```bash
python -m pytest tests/test_<relevant>.py -q
```

Run broader suites when touching shared engine/helpers:

```bash
python tests/test_lorwyn.py
python tests/test_layer_nightmares.py
python tests/test_degenerate.py
python -m pytest tests/ -q
```
