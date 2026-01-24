# Hyperdraft Architecture: Event-Driven Card Engine

## Philosophy

MTG's rules evolved over 30 years, accumulating distinct systems:
- The Stack (responses)
- Priority (who acts)
- Layers (continuous effects)
- State-Based Actions (automatic cleanup)
- Replacement Effects (event modification)
- Triggered Abilities (reactions)

**Hyperdraft's premise**: These are all the same thing viewed differently.

Everything is an **Event**. Everything else is an **Interceptor** on that event.

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      EVENT BUS                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Event emitted → Interceptor Chain → Final Result   │    │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    INTERCEPTORS                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Transform │  │  React   │  │  Prevent │  │  Query   │    │
│  │ (replace) │  │ (trigger)│  │  (deny)  │  │ (modify) │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    GAME STATE                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│  │ Objects  │  │  Zones   │  │ Players  │                   │
│  └──────────┘  └──────────┘  └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

---

## The Three Primitives

### 1. Events

An Event is an atomic thing that happens or is about to happen.

```typescript
interface Event {
  id: EventId;
  type: EventType;
  source: ObjectId | null;      // What caused this
  controller: PlayerId | null;  // Who controls the source
  payload: EventPayload;        // Type-specific data
  timestamp: number;            // When it was created

  // Event lifecycle
  status: 'pending' | 'resolving' | 'resolved' | 'prevented';
}
```

**Core Event Types** (the atoms everything else is built from):

```typescript
type EventType =
  // Object lifecycle
  | 'OBJECT_CREATED'        // Token/copy comes into existence
  | 'OBJECT_DESTROYED'      // Permanent destruction
  | 'ZONE_CHANGE'           // Object moves between zones

  // State changes
  | 'TAP'                   // Object taps
  | 'UNTAP'                 // Object untaps
  | 'COUNTER_ADDED'         // Counter placed on object
  | 'COUNTER_REMOVED'       // Counter removed from object

  // Combat
  | 'ATTACK_DECLARED'       // Creature declared as attacker
  | 'BLOCK_DECLARED'        // Creature declared as blocker
  | 'DAMAGE'                // Damage dealt to object/player

  // Resources
  | 'MANA_PRODUCED'         // Mana added to pool
  | 'MANA_SPENT'            // Mana paid for cost
  | 'LIFE_CHANGE'           // Life gained or lost

  // Card actions
  | 'DRAW'                  // Card drawn
  | 'DISCARD'               // Card discarded
  | 'CAST'                  // Spell cast (goes to pending zone)
  | 'ACTIVATE'              // Ability activated

  // Turn structure
  | 'PHASE_START'           // Phase begins
  | 'PHASE_END'             // Phase ends
  | 'TURN_START'            // Turn begins
  | 'TURN_END'              // Turn ends
  | 'PRIORITY_PASS'         // Player passes priority

  // Meta
  | 'GAME_START'
  | 'GAME_END'
  | 'PLAYER_LOSES'
  | 'PLAYER_WINS';
```

**Key insight**: Complex actions are just sequences of atomic events.

"Cast a creature spell" = `CAST` → `ZONE_CHANGE(stack→battlefield)` → `OBJECT_CREATED(on battlefield)`

### 2. Interceptors

An Interceptor is a function that watches the event stream and can intervene.

```typescript
interface Interceptor {
  id: InterceptorId;
  source: ObjectId;             // The card that created this
  controller: PlayerId;

  // What events does this care about?
  filter: EventFilter;

  // When in the chain does this run?
  priority: InterceptorPriority;

  // What does it do?
  handler: InterceptorHandler;

  // Lifecycle
  duration: Duration;           // Until end of turn, while in play, etc.
  usesRemaining: number | null; // For one-shot effects
}

type InterceptorPriority =
  | 'TRANSFORM'   // Runs first - can change the event itself
  | 'PREVENT'     // Can stop the event entirely
  | 'REACT'       // Runs after - creates new events in response
  | 'QUERY';      // Always-on - modifies how state is read

type InterceptorHandler = (
  event: Event,
  state: GameState,
  context: InterceptorContext
) => InterceptorResult;

type InterceptorResult =
  | { action: 'pass' }                           // Do nothing
  | { action: 'transform', newEvent: Event }     // Modify the event
  | { action: 'prevent' }                        // Cancel the event
  | { action: 'react', newEvents: Event[] }      // Queue new events
  | { action: 'replace', newEvents: Event[] };   // Replace with different events
```

**This unifies everything:**

| MTG Concept | Hyperdraft Interceptor |
|-------------|------------------------|
| Replacement Effect | `TRANSFORM` priority interceptor |
| Prevention Effect | `PREVENT` priority interceptor |
| Triggered Ability | `REACT` priority interceptor |
| Continuous Effect | `QUERY` priority interceptor |
| State-Based Action | System-level `REACT` interceptor |

### 3. Objects

Everything in the game is an Object with the same shape:

```typescript
interface GameObject {
  id: ObjectId;

  // Identity
  name: string;
  baseCard: CardDefinition | null;  // null for tokens/copies

  // Ownership
  owner: PlayerId;
  controller: PlayerId;

  // Location
  zone: ZoneId;

  // Characteristics (base values - interceptors modify reads)
  characteristics: {
    types: Set<CardType>;
    subtypes: Set<string>;
    supertypes: Set<string>;
    colors: Set<Color>;
    manaCost: ManaCost | null;
    power: number | null;
    toughness: number | null;
    abilities: AbilityDefinition[];
  };

  // State
  state: {
    tapped: boolean;
    flipped: boolean;
    faceDown: boolean;
    damage: number;
    counters: Map<CounterType, number>;
    attachedTo: ObjectId | null;
    attachments: ObjectId[];
  };

  // Interceptors this object has registered
  interceptors: InterceptorId[];

  // Metadata
  enteredZoneAt: number;  // Timestamp
  createdAt: number;
}
```

---

## The Event Pipeline

When something happens, it flows through this pipeline:

```
1. EVENT CREATED
   │
   ▼
2. TRANSFORM PHASE
   │ All TRANSFORM interceptors run (in timestamp order)
   │ Event may be modified or replaced
   │
   ▼
3. PREVENT PHASE
   │ All PREVENT interceptors run
   │ If any returns 'prevent', event is cancelled
   │
   ▼
4. RESOLUTION
   │ Event actually happens
   │ Game state is modified
   │
   ▼
5. REACT PHASE
   │ All REACT interceptors run
   │ New events are queued
   │
   ▼
6. PROCESS QUEUE
   │ If new events were queued, process them (goto 1)
   │ This is how "triggers trigger triggers" works
   │
   ▼
7. DONE
```

### Example: Damage with Lifelink

Card A has "Whenever this creature deals damage, you gain that much life" (lifelink).

```typescript
// Lifelink registers a REACT interceptor
{
  filter: {
    type: 'DAMAGE',
    where: (event, state) => event.source === thisCard.id
  },
  priority: 'REACT',
  handler: (event) => ({
    action: 'react',
    newEvents: [{
      type: 'LIFE_CHANGE',
      payload: {
        player: event.controller,
        amount: event.payload.amount
      }
    }]
  })
}
```

Card B has "If you would gain life, you gain twice that much instead".

```typescript
// Double life registers a TRANSFORM interceptor
{
  filter: {
    type: 'LIFE_CHANGE',
    where: (event) => event.payload.amount > 0 && event.payload.player === myPlayer
  },
  priority: 'TRANSFORM',
  handler: (event) => ({
    action: 'transform',
    newEvent: {
      ...event,
      payload: { ...event.payload, amount: event.payload.amount * 2 }
    }
  })
}
```

The pipeline:
1. `DAMAGE` event created (3 damage)
2. Transform phase: nothing transforms damage
3. Prevent phase: nothing prevents
4. Resolution: damage happens
5. React phase: Lifelink queues `LIFE_CHANGE(+3)`
6. Process queue:
   - `LIFE_CHANGE(+3)` created
   - Transform phase: Double-life transforms to `LIFE_CHANGE(+6)`
   - Resolution: gain 6 life

**Cards don't know about each other. Complexity emerges.**

---

## Handling "The Stack" (Responses)

MTG's stack lets players respond to spells/abilities. We model this with **pending events**.

```typescript
interface PendingEvent extends Event {
  status: 'pending';
  canBeRespondedTo: boolean;
  responsesAllowed: PlayerId[];  // Who can still respond
}
```

When a spell is cast:
1. `CAST` event created with `status: 'pending'`
2. Priority passes between players
3. Players can create new pending events (responses)
4. When all players pass, oldest pending event resolves
5. After resolution, priority passes again

```typescript
// The response loop
async function priorityLoop(state: GameState): Promise<void> {
  while (state.pendingEvents.length > 0) {
    for (const player of state.turnOrder) {
      const action = await getPlayerAction(player, state);

      if (action.type === 'PASS') {
        state.passes.add(player);
      } else if (action.type === 'CAST' || action.type === 'ACTIVATE') {
        // New pending event - reset passes
        state.pendingEvents.push(createPendingEvent(action));
        state.passes.clear();
      }

      // All players passed?
      if (state.passes.size === state.players.length) {
        // Resolve most recent pending event
        const event = state.pendingEvents.pop()!;
        await resolveEvent(event, state);
        state.passes.clear();
      }
    }
  }
}
```

---

## Handling Continuous Effects (Goodbye Layers)

MTG's layer system exists because continuous effects can conflict. "All creatures get +1/+1" vs "Target creature's power becomes 0" - which wins?

**Hyperdraft approach**: There are no "continuous effects" that modify state. Instead:

1. Base state is always stored
2. `QUERY` interceptors modify how you *read* state
3. Query interceptors run in timestamp order (older first)
4. The final read value is what you see

```typescript
function getCreaturePower(creatureId: ObjectId, state: GameState): number {
  const creature = state.objects.get(creatureId);
  let power = creature.characteristics.power;

  // Apply all QUERY interceptors that affect power
  const queries = state.interceptors
    .filter(i => i.priority === 'QUERY')
    .filter(i => i.filter.matches({ type: 'QUERY_POWER', target: creatureId }))
    .sort((a, b) => a.source.createdAt - b.source.createdAt);

  for (const interceptor of queries) {
    power = interceptor.handler({ currentValue: power, creature, state });
  }

  // Add counters last (always after other modifications)
  power += creature.state.counters.get('+1/+1') ?? 0;
  power -= creature.state.counters.get('-1/-1') ?? 0;

  return power;
}
```

**Query categories** (like MTG's layers, but simpler):

```typescript
type QueryType =
  | 'QUERY_COPY'        // What is this a copy of?
  | 'QUERY_CONTROL'     // Who controls this?
  | 'QUERY_TYPES'       // What types does this have?
  | 'QUERY_COLORS'      // What colors is this?
  | 'QUERY_ABILITIES'   // What abilities does this have?
  | 'QUERY_POWER'       // What's the power?
  | 'QUERY_TOUGHNESS';  // What's the toughness?
```

Within each query type, interceptors run in timestamp order. This handles 90% of cases.

For the remaining edge cases (dependencies), we add:

```typescript
interface QueryInterceptor extends Interceptor {
  // Optional: "run me after this other interceptor"
  dependsOn?: InterceptorId[];
}
```

---

## Zones

Zones are just tagged collections. No special behavior - that's handled by interceptors.

```typescript
type ZoneType =
  | 'LIBRARY'      // Hidden, ordered
  | 'HAND'         // Hidden to opponents
  | 'BATTLEFIELD'  // Visible, shared
  | 'GRAVEYARD'    // Visible, ordered
  | 'EXILE'        // Visible, shared
  | 'STACK'        // Visible, ordered (pending events)
  | 'COMMAND';     // Visible (commanders, emblems)

interface Zone {
  id: ZoneId;
  type: ZoneType;
  owner: PlayerId | 'shared';
  objects: ObjectId[];

  // For ordered zones
  isOrdered: boolean;
}
```

Zone changes are just `ZONE_CHANGE` events that interceptors can react to:

```typescript
// "When a creature enters the battlefield, draw a card"
{
  filter: {
    type: 'ZONE_CHANGE',
    where: (e) =>
      e.payload.to.type === 'BATTLEFIELD' &&
      state.objects.get(e.payload.objectId).characteristics.types.has('creature')
  },
  priority: 'REACT',
  handler: () => ({
    action: 'react',
    newEvents: [{ type: 'DRAW', payload: { player: myPlayer, count: 1 } }]
  })
}
```

---

## State-Based Actions

SBAs in MTG are automatic game rules (creature with 0 toughness dies). In Hyperdraft, these are just system-level `REACT` interceptors that are always active:

```typescript
const SYSTEM_INTERCEPTORS: Interceptor[] = [
  // Creature with 0 or less toughness dies
  {
    id: 'SBA_ZERO_TOUGHNESS',
    source: 'SYSTEM',
    filter: { type: 'ANY' },  // Check after every event
    priority: 'REACT',
    handler: (event, state) => {
      const dying = state.battlefield
        .filter(obj => obj.characteristics.types.has('creature'))
        .filter(obj => getToughness(obj, state) <= 0);

      if (dying.length === 0) return { action: 'pass' };

      return {
        action: 'react',
        newEvents: dying.map(obj => ({
          type: 'ZONE_CHANGE',
          payload: { objectId: obj.id, from: 'battlefield', to: 'graveyard' }
        }))
      };
    }
  },

  // Creature with lethal damage dies
  {
    id: 'SBA_LETHAL_DAMAGE',
    source: 'SYSTEM',
    filter: { type: 'ANY' },
    priority: 'REACT',
    handler: (event, state) => {
      const dying = state.battlefield
        .filter(obj => obj.characteristics.types.has('creature'))
        .filter(obj => obj.state.damage >= getToughness(obj, state));

      // ... same pattern
    }
  },

  // Player at 0 life loses
  {
    id: 'SBA_ZERO_LIFE',
    source: 'SYSTEM',
    filter: { type: 'LIFE_CHANGE' },
    priority: 'REACT',
    handler: (event, state) => {
      const losers = state.players.filter(p => p.life <= 0);
      return {
        action: 'react',
        newEvents: losers.map(p => ({ type: 'PLAYER_LOSES', payload: { player: p.id } }))
      };
    }
  }
];
```

---

## Card Definition Format

Cards are just collections of interceptors:

```yaml
name: "Lightning Bolt"
cost: "{R}"
types: [instant]
text: "Deal 3 damage to any target."

effects:
  - type: spell
    targets:
      - filter: { or: [creature, player, planeswalker] }
    resolution:
      - event: DAMAGE
        payload:
          target: $target[0]
          amount: 3
          source: $self
```

```yaml
name: "Mentor of the Meek"
cost: "{2}{W}"
types: [creature]
subtypes: [human, soldier]
power: 2
toughness: 2
text: "Whenever another creature with power 2 or less enters the battlefield under your control, you may pay {1}. If you do, draw a card."

interceptors:
  - trigger: ZONE_CHANGE
    filter:
      to: battlefield
      objectFilter:
        types: [creature]
        controller: $controller
        not: { id: $self }
        where: "power <= 2"
    optional: true
    cost: "{1}"
    resolution:
      - event: DRAW
        payload:
          player: $controller
          count: 1
```

```yaml
name: "Furnace of Rath"
cost: "{1}{R}{R}{R}"
types: [enchantment]
text: "If a source would deal damage to a permanent or player, it deals double that damage instead."

interceptors:
  - priority: TRANSFORM
    trigger: DAMAGE
    handler:
      action: transform
      modify:
        payload.amount: "* 2"
```

---

## Why This Might Work

### Emergent Complexity
Cards don't need to know about each other. They just register interceptors. Wild interactions emerge naturally from the pipeline.

### Uniform Mental Model
Players (and AI) only need to understand one thing: events flow through interceptors. No separate rules for triggers vs replacements vs continuous effects.

### Easier to Implement
One event pipeline, one interceptor system. Not separate subsystems for stack, layers, SBAs, etc.

### Easier to Test
Every interaction is traceable through the event log. "Why did X happen?" - look at the event chain.

### AI-Friendly
AI can reason about interceptors uniformly. "What happens if I emit event X?" - simulate the pipeline.

---

## Open Questions

1. **Performance**: With many interceptors, every event checks many filters. Need efficient indexing.

2. **Infinite loops**: Interceptors can create events that trigger interceptors. Need loop detection.

3. **Ordering edge cases**: Timestamp ordering handles most cases, but what about simultaneous triggers from the same card?

4. **Hidden information**: How do interceptors handle face-down cards, hidden hands?

5. **Network play**: Event sourcing makes this easier, but need to handle hidden info.

---

## Next Steps

1. **Prototype the event pipeline** - Core event types, interceptor registration, resolution
2. **Build a few test cards** - Lightning Bolt, a creature with a trigger, a continuous effect
3. **Test interactions** - Do unexpected combinations work correctly?
4. **Add the stack** - Pending events and priority passing
5. **Build a minimal UI** - Text-based to start

---

## Appendix: MTG → Hyperdraft Translation

| MTG Concept | Hyperdraft Equivalent |
|-------------|----------------------|
| Casting a spell | `CAST` event → pending → resolve → `ZONE_CHANGE` to battlefield |
| Activated ability | `ACTIVATE` event → pending → resolve → effect events |
| Triggered ability | `REACT` interceptor creates events |
| Replacement effect | `TRANSFORM` interceptor modifies event |
| Prevention effect | `PREVENT` interceptor cancels event |
| Continuous effect | `QUERY` interceptor modifies reads |
| State-based action | System `REACT` interceptor |
| The Stack | Pending events queue |
| Priority | Who can add pending events |
| Layers | Query interceptor ordering |
| Timestamps | `createdAt` field on interceptors |
| Zones | Tagged collections of objects |
| Counters | `state.counters` Map on objects |
