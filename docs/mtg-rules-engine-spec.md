# Magic: The Gathering Rules Engine Technical Specification

## Executive Summary

This document provides a comprehensive technical specification for implementing a Magic: The Gathering (MTG) rules engine similar to MTG Arena. MTG is computationally one of the most complex games ever created - research has proven it to be Turing-complete, meaning there exist game states where determining the winner is theoretically undecidable. This specification covers the major systems, existing implementations, architecture recommendations, and scope estimates for building such an engine.

---

## 1. MTG Comprehensive Rules Overview

### 1.1 Document Structure

The MTG Comprehensive Rules is the authoritative document for all Magic rules, currently **292 pages** as of June 2024. The document uses a hierarchical numbering system where rules are divided into subrules (e.g., 704.5a, 704.5b). Notably, subrules skip letters "l" and "o" to avoid confusion with numbers "1" and "0".

**Major Rule Sections:**
- **Section 1**: Game Concepts (100-199)
- **Section 2**: Parts of a Card (200-299)
- **Section 3**: Card Types (300-399)
- **Section 4**: Zones (400-499)
- **Section 5**: Turn Structure (500-599)
- **Section 6**: Spells, Abilities, and Effects (600-699)
- **Section 7**: Additional Rules (700-799) - includes State-Based Actions, Layers
- **Section 8**: Multiplayer Rules (800-899)
- **Section 9**: Casual Variants (900-999)

### 1.2 Core Systems That Must Be Implemented

#### 1.2.1 The Stack (Rule 405)
The stack is a shared zone where spells and abilities wait to resolve. Key properties:
- Last-in, first-out (LIFO) resolution order
- Spells, activated abilities, and triggered abilities all use the stack
- Mana abilities do NOT use the stack (they resolve immediately)
- The stack exists at all times (even when empty)

#### 1.2.2 Priority System (Rule 116)
Priority determines which player can take actions at any given moment:
- **Rule 116.3a**: Active player receives priority at the beginning of most steps/phases
- **Rule 116.3b**: Active player receives priority after a spell/ability resolves
- **Rule 116.3c**: After casting/activating, that player retains priority
- **Rule 116.3d**: Players can pass priority
- When all players pass in succession with an empty stack, the phase/step ends
- When all players pass with items on the stack, the top item resolves

#### 1.2.3 Phases and Steps (Rule 500-514)
Five phases per turn, subdivided into steps:

```
BEGINNING PHASE
├── Untap Step (no priority)
├── Upkeep Step
└── Draw Step

FIRST MAIN PHASE

COMBAT PHASE
├── Beginning of Combat Step
├── Declare Attackers Step
├── Declare Blockers Step
├── Combat Damage Step (may have two: first strike, then regular)
└── End of Combat Step

SECOND MAIN PHASE

ENDING PHASE
├── End Step
└── Cleanup Step (normally no priority)
```

#### 1.2.4 State-Based Actions (Rule 704)
Automatic game actions checked whenever a player would receive priority:

**Player SBAs:**
- 704.5a: Player at 0 or less life loses
- 704.5b: Player who drew from empty library loses
- 704.5c: Player with 10+ poison counters loses

**Permanent SBAs:**
- 704.5d: Tokens outside battlefield cease to exist
- 704.5e: Spell copies outside stack cease to exist
- 704.5f: Creatures with 0 or less toughness die (no regeneration)
- 704.5g: Creatures with lethal damage are destroyed
- 704.5h: Creatures damaged by deathtouch are destroyed
- 704.5i: Planeswalkers with 0 loyalty die
- 704.5j: Legend rule (duplicate legendaries)
- 704.5k: World rule (duplicate world permanents)
- 704.5n-q: Illegal attachments (Auras, Equipment, Fortifications)
- 704.5r: +1/+1 and -1/-1 counter annihilation
- 704.5v-w: Battle-specific rules
- 704.5y: Role token uniqueness

**SBA Processing Loop:**
1. Check all SBA conditions
2. Perform all applicable SBAs simultaneously
3. If any SBAs occurred, repeat from step 1
4. Put all waiting triggered abilities on the stack
5. Repeat check; if no SBAs and no triggers, player gets priority

#### 1.2.5 Layers System (Rule 613)
Continuous effects are applied in a specific order:

| Layer | Effect Type |
|-------|-------------|
| 1 | Copy effects |
| 2 | Control-changing effects |
| 3 | Text-changing effects |
| 4 | Type-changing effects |
| 5 | Color-changing effects |
| 6 | Ability-adding/removing effects |
| 7 | Power/toughness-changing effects |

**Layer 7 Sublayers:**
- 7a: Characteristic-defining abilities
- 7b: Effects that set P/T to specific values
- 7c: Effects that modify P/T without setting
- 7d: P/T changes from counters
- 7e: Effects that switch P/T

**Conflict Resolution:**
- **Timestamps**: Later effects win within same layer
- **Dependencies**: If effect A's existence depends on effect B, B applies first

---

## 2. Existing Open Source Implementations

### 2.1 Forge

**Repository:** [github.com/Card-Forge/forge](https://github.com/Card-Forge/forge)

**Technology Stack:**
- Language: Java 17+
- Platforms: Windows, Mac, Linux, Android (11+, 6GB RAM minimum)

**Architecture Approach:**
- **Script-based card definitions** - Cards defined in text files, not Java code
- Uses a declarative scripting API in `/res/cardsfolder`
- Does NOT require programming knowledge to add cards

**Card Definition Format Example:**
```
Name:Lightning Bolt
ManaCost:R
Types:Instant
Oracle:Lightning Bolt deals 3 damage to any target.
A:SP$ DealDamage | Cost$ R | ValidTgts$ Creature,Player,Planeswalker | TgtPrompt$ Select any target | NumDmg$ 3 | SpellDescription$ CARDNAME deals 3 damage to any target.
```

**Key Features:**
- Single-player and online multiplayer
- Adventure mode with overworld exploration
- AI opponents
- Most accessible for card contributors (no Java required)

**Strengths:**
- Largest card pool of open-source engines
- Card scripting allows rapid card addition
- Strong AI implementation

**Weaknesses:**
- Script language has limitations for complex cards
- Less precise rules enforcement than XMage

### 2.2 XMage

**Repository:** [github.com/magefree/mage](https://github.com/magefree/mage)

**Technology Stack:**
- Language: Java
- Build System: Maven
- CI/CD: Travis CI
- Architecture: Client-Server with socket communication

**Statistics:**
- 1.8+ million lines of code
- 47,000+ commits
- 28,000+ unique cards implemented
- 73,000+ reprints supported

**Architecture (5 Main Modules):**
1. **Mage** - Core game logic
2. **Mage.Sets** - Card implementations and set definitions
3. **Mage.Server** - Server-side networking and game hosting
4. **Mage.Client** - GUI client
5. **Mage.Common** - Shared communication layer

**Design Patterns Used:**
- **Singletons** (serialization-safe via enums) for card types
- **Factory Pattern**: PlayerFactory, GameFactory
- **Plugin Architecture**: Extensible player types and game modes

**Card Implementation Approach:**
Each card is a Java class extending `CardImpl`:
```java
public class LightningBolt extends CardImpl {
    public LightningBolt(UUID ownerId, CardSetInfo setInfo) {
        super(ownerId, setInfo, new CardType[]{CardType.INSTANT}, "{R}");
        this.getSpellAbility().addEffect(new DamageTargetEffect(3));
        this.getSpellAbility().addTarget(new TargetAnyTarget());
    }
}
```

**Strengths:**
- Full rules enforcement
- Client-server architecture enables online play
- Extensive test coverage (Mage.Tests, Mage.Verify modules)

**Weaknesses:**
- Requires Java knowledge to add cards
- More complex development environment setup
- Larger codebase to navigate

### 2.3 Cockatrice

**Repository:** [github.com/Cockatrice/Cockatrice](https://github.com/Cockatrice/Cockatrice)

**Technology Stack:**
- Language: C++ with Qt framework
- License: GPLv2

**Architecture:**
- **NO RULES ENFORCEMENT** - Virtual tabletop only
- Client-server model (Servatrice server component)
- Docker support for server deployment

**Key Characteristics:**
- Players manually enforce rules
- Supports any card game (preconfigured for MTG)
- Lightweight compared to rules engines
- Anti-cheat through server-side verification of moves (not rules)

**Use Case:**
Best for experienced players who want minimal overhead and maximum flexibility. Not suitable as a reference for rules engine implementation.

### 2.4 MTG Arena (Commercial Reference)

**Technology Stack:**
- Game Rules Engine (GRE): C++ and CLIPS (LISP variant)
- Game Rules Parser (GRP): Python

**Architecture - "Naps and Whiteboards" Model:**
1. GRE knows basic Magic rules (priority, phases, casting steps)
2. GRE does NOT know individual card behaviors
3. GRP parses English card text into CLIPS rules
4. ~80% of new cards work automatically through parsing
5. ~20% require manual GRP updates

**Key Insight:**
The engine maintains a "whiteboard" (game state) that rule scripts can modify. The core engine just processes the whiteboard state without understanding card-specific logic.

### 2.5 Other Notable Projects

| Project | Language | Notes |
|---------|----------|-------|
| [mtg-python-engine](https://github.com/wanqizhu/mtg-python-engine) | Python | Educational implementation |
| [MTG-Paradox-Engine](https://github.com/MTG-Paradox-Engine/mtg-paradox-engine) | TypeScript | Modern web-based approach |
| [cardboard](https://github.com/Julian/cardboard) | Python | Documentation-focused |
| mtg-sdk-rust | Rust | API wrapper, not rules engine |

---

## 3. Core Systems Required

### 3.1 Game State Representation

The game state is the complete snapshot of all game information at any moment.

```
GameState
├── Players[]
│   ├── life: number
│   ├── poisonCounters: number
│   ├── manaPool: ManaPool
│   ├── landPlaysRemaining: number
│   ├── hasLost: boolean
│   └── commanderDamageReceived: Map<CommanderId, number>
├── Zones
│   ├── libraries: Map<PlayerId, Zone>
│   ├── hands: Map<PlayerId, Zone>
│   ├── graveyards: Map<PlayerId, Zone>
│   ├── battlefield: Zone (shared)
│   ├── stack: Zone (shared, ordered)
│   ├── exile: Zone (shared)
│   └── command: Zone (shared)
├── TurnState
│   ├── activePlayer: PlayerId
│   ├── priorityPlayer: PlayerId
│   ├── phase: Phase
│   ├── step: Step
│   └── turnNumber: number
├── CombatState
│   ├── attackers: Map<CreatureId, AttackTarget>
│   ├── blockers: Map<CreatureId, CreatureId[]>
│   └── damageAssignment: Map<CreatureId, DamageAssignment>
├── ContinuousEffects[]
├── DelayedTriggers[]
├── ReplacementEffects[]
└── TurnHistory[]
```

### 3.2 Object Representation

Every game object (card, token, ability, emblem) needs comprehensive representation:

```
GameObject
├── id: UniqueId
├── name: string
├── owner: PlayerId
├── controller: PlayerId
├── zone: ZoneId
├── characteristics
│   ├── types: CardType[]
│   ├── subtypes: Subtype[]
│   ├── supertypes: Supertype[]
│   ├── colors: Color[]
│   ├── manaCost: ManaCost
│   ├── manaValue: number
│   ├── power: number (base)
│   ├── toughness: number (base)
│   ├── loyalty: number (base)
│   └── abilities: Ability[]
├── status
│   ├── tapped: boolean
│   ├── flipped: boolean
│   ├── faceDown: boolean
│   ├── phased: boolean
│   ├── transformed: boolean
│   └── damage: number
├── counters: Map<CounterType, number>
├── attachments: ObjectId[]
├── attachedTo: ObjectId?
└── timestamps
    ├── enteredZone: Timestamp
    └── effectTimestamps: Map<EffectId, Timestamp>
```

### 3.3 Turn Structure Implementation

```typescript
class TurnManager {
    phases = [
        new BeginningPhase([
            new UntapStep({ hasPriority: false }),
            new UpkeepStep(),
            new DrawStep()
        ]),
        new MainPhase(),
        new CombatPhase([
            new BeginningOfCombatStep(),
            new DeclareAttackersStep(),
            new DeclareBlockersStep(),
            new CombatDamageStep(), // May split for first strike
            new EndOfCombatStep()
        ]),
        new MainPhase(),
        new EndingPhase([
            new EndStep(),
            new CleanupStep({ hasPriority: false }) // Usually
        ])
    ];

    async runStep(step: Step) {
        // 1. Perform turn-based actions
        await step.performTurnBasedActions();

        // 2. Check state-based actions
        await this.processStateBasedActions();

        // 3. Put triggered abilities on stack
        await this.putTriggersOnStack();

        // 4. Active player gets priority (if step has priority)
        if (step.hasPriority) {
            await this.priorityLoop();
        }
    }
}
```

### 3.4 Priority and Stack System

```typescript
class PrioritySystem {
    async priorityLoop() {
        let consecutivePasses = 0;
        let currentPlayer = this.activePlayer;

        while (true) {
            // Check SBAs and triggers before each priority grant
            await this.checkStateBasedActions();
            await this.putTriggersOnStack();

            // Grant priority
            const action = await this.getPlayerAction(currentPlayer);

            if (action.type === 'PASS') {
                consecutivePasses++;

                // All players passed
                if (consecutivePasses >= this.playerCount) {
                    if (this.stack.isEmpty()) {
                        return; // Phase/step ends
                    } else {
                        await this.resolveTopOfStack();
                        consecutivePasses = 0;
                        currentPlayer = this.activePlayer;
                        continue;
                    }
                }
            } else {
                consecutivePasses = 0;
                await this.executeAction(action);
                // Player who acted retains priority (116.3c)
                continue;
            }

            currentPlayer = this.getNextPlayer(currentPlayer);
        }
    }

    async resolveTopOfStack() {
        const item = this.stack.pop();

        // Check if all targets are still legal
        if (!this.hasLegalTargets(item)) {
            // Spell/ability is countered (fizzles)
            if (item.isSpell) {
                this.moveToGraveyard(item);
            }
            return;
        }

        // Resolve the spell or ability
        await item.resolve(this.gameState);

        // If spell, move to appropriate zone
        if (item.isSpell) {
            if (item.isPermanent) {
                this.moveToBattlefield(item);
            } else {
                this.moveToGraveyard(item);
            }
        }
    }
}
```

### 3.5 Mana System

```typescript
class ManaPool {
    mana: Map<ManaType, ManaUnit[]> = new Map();

    // ManaTypes: WHITE, BLUE, BLACK, RED, GREEN, COLORLESS

    add(type: ManaType, amount: number, restrictions?: ManaRestriction[]) {
        for (let i = 0; i < amount; i++) {
            this.mana.get(type).push({
                type,
                restrictions, // e.g., "only for creature spells"
                source: sourceId
            });
        }
    }

    canPay(cost: ManaCost): boolean {
        // Complex algorithm considering:
        // - Generic mana can be paid with any color
        // - Hybrid mana (W/U) can be paid with either
        // - Phyrexian mana can be paid with life
        // - Snow mana requirements
        // - Mana restrictions
    }

    pay(cost: ManaCost): ManaPayment {
        // Returns the specific mana units used
        // Important for effects that care about mana spent
    }

    empty() {
        // Called at end of each step/phase
        // Triggers "mana empties" effects
        this.mana.clear();
    }
}

class ManaAbility {
    // Mana abilities are special:
    // 1. Don't use the stack
    // 2. Can't be responded to
    // 3. Can be activated during mana payment

    isManaAbility(): boolean {
        return this.hasNoTarget()
            && this.couldProduceMana()
            && !this.isLoyaltyAbility();
    }
}
```

### 3.6 Combat System

Post-Foundations rules (2024+) simplified damage assignment:

```typescript
class CombatManager {
    async declareAttackersStep() {
        // Active player declares all attackers simultaneously
        const attackDeclarations = await this.activePlayer.declareAttackers();

        for (const decl of attackDeclarations) {
            // Validate creature can attack
            if (!this.canAttack(decl.creature, decl.target)) {
                throw new IllegalAttackError();
            }

            // Tap attacking creatures (unless vigilance)
            if (!decl.creature.hasVigilance()) {
                decl.creature.tap();
            }

            // Pay attack costs if any
            await this.payAttackCosts(decl);
        }

        // Trigger "whenever attacks" abilities
        this.triggerAttackTriggers(attackDeclarations);
    }

    async declareBlockersStep() {
        // Defending player(s) declare blockers
        const blockDeclarations = await this.defendingPlayer.declareBlockers();

        for (const decl of blockDeclarations) {
            // Validate creature can block
            if (!this.canBlock(decl.blocker, decl.attacker)) {
                throw new IllegalBlockError();
            }
        }

        // REMOVED in Foundations: Damage assignment order
        // Attackers no longer need to order blockers

        // Trigger "whenever blocks" abilities
        this.triggerBlockTriggers(blockDeclarations);
    }

    async combatDamageStep(isFirstStrike: boolean = false) {
        const combatants = isFirstStrike
            ? this.getFirstStrikeCombatants()
            : this.getNormalCombatants();

        // Active player assigns damage for attackers
        for (const attacker of combatants.attackers) {
            if (attacker.isBlocked()) {
                // NEW in Foundations: Free damage distribution
                const assignment = await this.activePlayer.assignDamage(
                    attacker,
                    attacker.blockers
                );
                // No longer need to assign lethal before moving on
                // (except for trample)
            } else {
                // Unblocked - damage goes to defender
                this.assignDamageToDefender(attacker);
            }
        }

        // Defending player assigns damage for blockers
        for (const blocker of combatants.blockers) {
            const assignment = await this.defendingPlayer.assignDamage(
                blocker,
                [blocker.blocking]
            );
        }

        // All damage dealt simultaneously
        this.dealAllCombatDamage();
    }
}
```

### 3.7 Targeting System

```typescript
class TargetingSystem {
    validateTargets(spell: Spell, targets: Target[]): boolean {
        const requirements = spell.getTargetRequirements();

        for (let i = 0; i < requirements.length; i++) {
            const req = requirements[i];
            const target = targets[i];

            if (!this.isLegalTarget(target, req)) {
                return false;
            }
        }

        return true;
    }

    isLegalTarget(target: GameObject, requirement: TargetRequirement): boolean {
        // Check zone
        if (!requirement.zones.includes(target.zone)) {
            return false;
        }

        // Check characteristics
        if (!requirement.filter.matches(target)) {
            return false;
        }

        // Check protection and hexproof
        if (target.hasProtectionFrom(this.sourceController)) {
            return false;
        }

        if (target.hasHexproof() && !this.controlledBy(target.controller)) {
            return false;
        }

        if (target.hasShroud()) {
            return false;
        }

        // Check ward (still legal, but triggers ward)

        return true;
    }

    async onResolution(spell: Spell) {
        const targets = spell.targets;
        const stillLegal = targets.filter(t => this.isStillLegal(t, spell));

        // If NO targets are legal, spell is countered
        if (stillLegal.length === 0 && targets.length > 0) {
            return { countered: true };
        }

        // Otherwise, resolve with legal targets only
        return { legalTargets: stillLegal };
    }
}
```

### 3.8 State-Based Actions Processor

```typescript
class StateBasedActionProcessor {
    async process(): Promise<boolean> {
        let actionsPerformed = false;

        do {
            const actions = this.collectApplicableSBAs();

            if (actions.length === 0) {
                break;
            }

            // Perform all SBAs simultaneously
            await this.performSimultaneously(actions);
            actionsPerformed = true;

            // Repeat check
        } while (true);

        // After SBAs complete, put triggers on stack
        await this.putTriggeredAbilitiesOnStack();

        return actionsPerformed;
    }

    collectApplicableSBAs(): StateBasedAction[] {
        const actions: StateBasedAction[] = [];

        // Player SBAs
        for (const player of this.players) {
            if (player.life <= 0) {
                actions.push(new PlayerLosesAction(player, '704.5a'));
            }
            if (player.drewFromEmptyLibrary) {
                actions.push(new PlayerLosesAction(player, '704.5b'));
            }
            if (player.poisonCounters >= 10) {
                actions.push(new PlayerLosesAction(player, '704.5c'));
            }
        }

        // Battlefield SBAs
        for (const permanent of this.battlefield) {
            // Zero toughness
            if (permanent.isCreature() && permanent.getToughness() <= 0) {
                actions.push(new PutInGraveyardAction(permanent, '704.5f'));
            }

            // Lethal damage
            if (permanent.isCreature() &&
                permanent.getToughness() > 0 &&
                permanent.damage >= permanent.getToughness()) {
                actions.push(new DestroyAction(permanent, '704.5g'));
            }

            // Deathtouch damage
            if (permanent.isCreature() && permanent.hasDeathTouchDamage) {
                actions.push(new DestroyAction(permanent, '704.5h'));
            }

            // Zero loyalty
            if (permanent.isPlaneswalker() && permanent.getLoyalty() <= 0) {
                actions.push(new PutInGraveyardAction(permanent, '704.5i'));
            }

            // Legend rule
            // ... etc
        }

        return actions;
    }
}
```

### 3.9 Layers System Implementation

```typescript
class LayerSystem {
    layers = [
        new CopyLayer(),           // Layer 1
        new ControlLayer(),        // Layer 2
        new TextChangeLayer(),     // Layer 3
        new TypeChangeLayer(),     // Layer 4
        new ColorChangeLayer(),    // Layer 5
        new AbilityLayer(),        // Layer 6
        new PTLayer()              // Layer 7 (with sublayers)
    ];

    calculateCharacteristics(permanent: Permanent): CalculatedCharacteristics {
        // Start with copiable values
        let characteristics = permanent.getCopiableValues();

        // Apply each layer in order
        for (const layer of this.layers) {
            characteristics = layer.apply(
                permanent,
                characteristics,
                this.getEffectsForLayer(layer)
            );
        }

        return characteristics;
    }

    getEffectsForLayer(layer: Layer): ContinuousEffect[] {
        const effects = this.continuousEffects
            .filter(e => e.appliesInLayer(layer))
            .sort((a, b) => this.compareEffects(a, b, layer));

        return effects;
    }

    compareEffects(a: Effect, b: Effect, layer: Layer): number {
        // Check dependencies first
        if (a.dependsOn(b, layer)) return 1;  // b applies first
        if (b.dependsOn(a, layer)) return -1; // a applies first

        // Otherwise, use timestamps
        return a.timestamp - b.timestamp;
    }
}

class PTLayer extends Layer {
    sublayers = ['7a', '7b', '7c', '7d', '7e'];

    apply(permanent: Permanent, chars: Characteristics, effects: Effect[]): Characteristics {
        // 7a: Characteristic-defining abilities
        for (const cda of this.getCDAs(permanent)) {
            chars = cda.apply(chars);
        }

        // 7b: Effects that SET P/T
        for (const effect of effects.filter(e => e.sublayer === '7b')) {
            chars.power = effect.power;
            chars.toughness = effect.toughness;
        }

        // 7c: Effects that MODIFY P/T (not from counters)
        for (const effect of effects.filter(e => e.sublayer === '7c')) {
            chars.power += effect.powerMod;
            chars.toughness += effect.toughnessMod;
        }

        // 7d: Counters
        chars.power += permanent.counters.get('+1/+1') ?? 0;
        chars.power -= permanent.counters.get('-1/-1') ?? 0;
        chars.toughness += permanent.counters.get('+1/+1') ?? 0;
        chars.toughness -= permanent.counters.get('-1/-1') ?? 0;

        // 7e: P/T switching effects
        for (const effect of effects.filter(e => e.sublayer === '7e')) {
            [chars.power, chars.toughness] = [chars.toughness, chars.power];
        }

        return chars;
    }
}
```

### 3.10 Zone Management

```typescript
class ZoneManager {
    zones: Map<ZoneType, Zone> = new Map();

    // Zone types and their properties
    zoneProperties = {
        LIBRARY: { hidden: true, ordered: true, ownerSpecific: true },
        HAND: { hidden: true, ordered: false, ownerSpecific: true },
        BATTLEFIELD: { hidden: false, ordered: false, ownerSpecific: false },
        GRAVEYARD: { hidden: false, ordered: true, ownerSpecific: true },
        STACK: { hidden: false, ordered: true, ownerSpecific: false },
        EXILE: { hidden: false, ordered: false, ownerSpecific: false },
        COMMAND: { hidden: false, ordered: false, ownerSpecific: false }
    };

    moveObject(object: GameObject, from: Zone, to: Zone) {
        // Zone change creates a NEW object (Rule 400.7)
        const newObject = object.createNewInstance();

        // Apply replacement effects
        const finalDestination = this.applyReplacementEffects(
            newObject, from, to
        );

        // Remove from old zone
        from.remove(object);

        // Add to new zone
        finalDestination.add(newObject);

        // Trigger zone change triggers
        this.triggerZoneChangeTriggers(object, from, finalDestination);

        return newObject;
    }
}
```

---

## 4. Complexity Assessment

### 4.1 Why MTG is Computationally Complex

Research has proven that Magic: The Gathering is **Turing-complete**, meaning:
- There exist game states where determining the winner is theoretically undecidable
- A Universal Turing Machine can be constructed within the game rules
- This is the most computationally complex real-world game documented

### 4.2 Primary Implementation Challenges

#### 4.2.1 Card Interaction Combinatorics
- **27,000+ unique cards** with distinct mechanical behaviors
- **73,000+ total printings** to track
- Every new card potentially interacts with every existing card
- Edge cases multiply exponentially

#### 4.2.2 The Layers System
The continuous effects layer system is notoriously complex:
- 7 layers with sublayers
- Timestamp ordering within layers
- Dependency exceptions that override timestamps
- Effects that create other effects
- Classic puzzle: Humility + Opalescence interactions

#### 4.2.3 Replacement Effects
Replacement effects modify events before they happen:
- Can chain (one replacement creates another)
- Player affected chooses order
- Must track "what would have happened" vs "what actually happens"
- Self-replacement effects (e.g., "if would draw, draw two instead")

#### 4.2.4 Triggered Abilities
- Triggers can trigger other triggers
- Must track "last known information" for triggers
- Objects can leave the zone that triggered them
- Abilities exist independently of their source (Rule 112.7a)

#### 4.2.5 Copy Effects
Copying is recursive and complex:
- What is copiable vs what isn't
- Copy of a copy
- Clones entering as copies of things that aren't creatures
- Token copies
- Copy effects during resolution

#### 4.2.6 Specific Problematic Card Categories

| Category | Example Cards | Challenge |
|----------|--------------|-----------|
| Wish effects | Burning Wish | External game zones |
| Replacement chains | Leyline of the Void + Rest in Peace | Effect ordering |
| Control changing | Gilded Drake | Ownership vs control tracking |
| Layer interactions | Blood Moon + Urborg | Dependency calculations |
| Extra turns/phases | Time Walk effects | Turn structure modification |
| Copying permanents | Clone variants | Copiable values calculation |
| Split second | Krosan Grip | Priority restrictions |
| Morph/disguise | Face-down creatures | Hidden information |

#### 4.2.7 Format-Specific Rules
Different formats add rule variations:
- **Commander**: 100-card singleton, command zone, commander damage, color identity
- **Two-Headed Giant**: Shared life total, simultaneous turns
- **Planechase**: Planar deck, planeswalking
- **Archenemy**: Scheme cards
- **Conspiracy/Draft matters**: Cards that affect drafting

### 4.3 MTG Arena's Solution

MTG Arena's "80/20 rule":
- 80% of cards can be automatically parsed from English rules text
- 20% require manual programming
- The 20% includes novel mechanics (e.g., Living Breakthrough's unique effect)

---

## 5. Architecture Recommendations

### 5.1 Language Recommendations

| Aspect | Recommendation | Rationale |
|--------|---------------|-----------|
| **Core Engine** | Rust or TypeScript | Type safety, performance (Rust) or ecosystem (TypeScript) |
| **Card Definitions** | DSL or JSON | Separates card data from engine logic |
| **AI/Solver** | Python or Rust | ML libraries (Python) or performance (Rust) |
| **Frontend** | TypeScript/React or Unity | Web deployment or rich graphics |

### 5.2 Recommended Architecture Pattern

**Event Sourcing + CQRS (Command Query Responsibility Segregation)**

```
┌─────────────────────────────────────────────────────────────┐
│                      Game Engine Core                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Command    │  │    Event     │  │   State          │  │
│  │   Handler    │──▶│    Store     │──▶│   Projector     │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│         │                                      │            │
│         ▼                                      ▼            │
│  ┌──────────────┐                    ┌──────────────────┐  │
│  │   Rules      │                    │   Game State     │  │
│  │   Validator  │                    │   (Read Model)   │  │
│  └──────────────┘                    └──────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    Subsystems                                │
├────────────┬────────────┬────────────┬──────────────────────┤
│  Priority  │   Stack    │   Combat   │   Continuous Effects │
│  System    │   Manager  │   Manager  │   (Layers)           │
├────────────┴────────────┴────────────┴──────────────────────┤
│                    Card System                               │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │    Card      │  │   Ability    │  │    Effect        │  │
│  │  Definitions │  │   Registry   │  │    Handlers      │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Key Design Patterns

#### 5.3.1 Command Pattern
Every game action is a command object:
```typescript
interface GameCommand {
    type: string;
    playerId: PlayerId;
    validate(state: GameState): ValidationResult;
    execute(state: GameState): GameEvent[];
}
```

#### 5.3.2 Event Sourcing
All state changes are events:
```typescript
type GameEvent =
    | { type: 'CARD_DRAWN', playerId: PlayerId, cardId: CardId }
    | { type: 'SPELL_CAST', spellId: SpellId, targets: Target[] }
    | { type: 'DAMAGE_DEALT', source: ObjectId, target: ObjectId, amount: number }
    | { type: 'CREATURE_DIED', creatureId: ObjectId }
    // ... hundreds more
```

Benefits:
- Perfect replay capability
- Easy debugging
- Undo support
- Network synchronization

#### 5.3.3 Visitor Pattern for Effects
```typescript
interface EffectVisitor {
    visitDamageEffect(effect: DamageEffect): void;
    visitDrawEffect(effect: DrawEffect): void;
    visitDestroyEffect(effect: DestroyEffect): void;
    // ... etc
}
```

#### 5.3.4 Strategy Pattern for AI
```typescript
interface AIStrategy {
    chooseMulliganDecision(hand: Card[]): MulliganDecision;
    chooseAttackers(state: GameState): AttackDeclaration[];
    chooseBlockers(state: GameState): BlockDeclaration[];
    choosePriorityAction(state: GameState): Action | 'PASS';
    chooseTargets(ability: Ability, legalTargets: Target[]): Target[];
}
```

### 5.4 Data Structures

#### 5.4.1 Game State (Immutable)
Use immutable data structures for:
- Easy state comparison
- Safe concurrent access
- Efficient copying for AI lookahead
- Built-in undo capability

```typescript
// Using Immer.js or similar
const nextState = produce(currentState, draft => {
    draft.players[0].life -= 3;
    draft.battlefield.push(newCreature);
});
```

#### 5.4.2 Zone Implementation
```typescript
interface Zone {
    type: ZoneType;
    objects: Map<ObjectId, GameObject>;

    // For ordered zones (library, graveyard, stack)
    order?: ObjectId[];
}
```

#### 5.4.3 Effect Registry
```typescript
class EffectRegistry {
    private continuousEffects: ContinuousEffect[] = [];
    private replacementEffects: ReplacementEffect[] = [];
    private triggerConditions: Map<TriggerType, TriggerHandler[]>;

    register(effect: Effect): void;
    unregister(effectId: EffectId): void;
    getApplicableEffects(event: GameEvent): Effect[];
}
```

### 5.5 Card Definition Format (Recommended DSL)

```yaml
# cards/lightning-bolt.yaml
name: Lightning Bolt
manaCost: "{R}"
types:
  - Instant
abilities:
  - type: spell
    effect:
      type: damage
      amount: 3
      targets:
        - filter: any_target
          count: 1
text: "Lightning Bolt deals 3 damage to any target."
```

Or a more complex card:

```yaml
# cards/snapcaster-mage.yaml
name: Snapcaster Mage
manaCost: "{1}{U}"
types:
  - Creature
subtypes:
  - Human
  - Wizard
power: 2
toughness: 1
abilities:
  - type: static
    keyword: flash
  - type: triggered
    trigger:
      type: zone_change
      destination: battlefield
      object: self
    effect:
      type: grant_ability
      targets:
        - filter: instant_or_sorcery
          zone: graveyard
          controller: you
          count: 1
      ability:
        keyword: flashback
        cost: mana_cost
      duration: end_of_turn
```

### 5.6 Testing Strategy

```
Test Pyramid:
├── Unit Tests (60%)
│   ├── Individual card abilities
│   ├── Mana cost parsing
│   ├── Layer calculations
│   └── State-based action checks
├── Integration Tests (30%)
│   ├── Full turn sequences
│   ├── Combat resolution
│   ├── Stack resolution
│   └── Multi-card interactions
└── End-to-End Tests (10%)
    ├── Complete games
    ├── Format rule compliance
    └── Edge case scenarios
```

---

## 6. Scope Estimate

### 6.1 Card Count Requirements

| MVP Level | Card Count | Supported Sets | Complexity |
|-----------|------------|----------------|------------|
| **Prototype** | 100-300 | Core mechanics demo | Low |
| **Alpha** | 1,000-2,000 | 2-3 recent Standard sets | Medium |
| **Beta** | 5,000-10,000 | Full Standard + popular Modern cards | High |
| **Production** | 15,000+ | Multiple formats | Very High |

### 6.2 Recommended MVP Card Selection

For a **1,500 card MVP**:

```
Core Mechanics Coverage:
├── Basic Lands (5 types × 4 art = 20)
├── Creatures with keywords (200+)
│   ├── Flying, First Strike, Deathtouch, Lifelink, Trample
│   ├── Vigilance, Reach, Menace, Haste
│   └── Flash, Hexproof, Indestructible
├── Instants and Sorceries (300+)
│   ├── Damage spells
│   ├── Card draw
│   ├── Removal (destroy, exile, bounce)
│   └── Counterspells
├── Enchantments (150+)
│   ├── Auras
│   └── Global enchantments
├── Artifacts (150+)
│   ├── Equipment
│   └── Mana rocks
├── Planeswalkers (50+)
└── Special cards for rule coverage
    ├── Copy effects
    ├── Control-changing
    ├── Type-changing
    └── Layer interaction tests
```

### 6.3 Development Timeline Estimate

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 1: Core Engine** | 3-4 months | Turn structure, priority, stack, zones |
| **Phase 2: Combat & Mana** | 2-3 months | Full combat system, mana abilities |
| **Phase 3: Card Framework** | 2-3 months | Card definition system, 200 cards |
| **Phase 4: Continuous Effects** | 2-3 months | Layers system, timestamps, dependencies |
| **Phase 5: Card Expansion** | 3-4 months | Scale to 1,500+ cards |
| **Phase 6: UI/UX** | 3-4 months | Playable interface |
| **Phase 7: AI** | 2-3 months | Basic AI opponent |
| **Phase 8: Polish** | 2-3 months | Testing, edge cases, optimization |

**Total: 19-27 months** for a production-quality MVP (1 developer)

Team scaling estimates:
- 3-person team: 8-12 months
- 5-person team: 5-8 months

### 6.4 Rules Complexity Metrics

| Rule Category | Estimated Implementation Effort |
|--------------|--------------------------------|
| Turn structure | Medium (well-defined) |
| Priority system | Medium (clear rules) |
| Stack resolution | Medium-High (interactions) |
| Mana system | Medium (many edge cases) |
| Combat | High (post-Foundations simpler) |
| State-based actions | Medium (enumerable) |
| Targeting | High (many conditions) |
| Layers | Very High (dependencies) |
| Replacement effects | Very High (chains) |
| Triggered abilities | High (timing, LKI) |
| Copy effects | Very High (recursive) |

### 6.5 Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Layer edge cases | High | High | Extensive test suite |
| Card interaction bugs | High | Medium | Incremental card addition |
| Performance issues | Medium | High | Event sourcing, profiling |
| Rules updates | High | Medium | Modular rule system |
| Scope creep | High | High | Strict MVP definition |

---

## 7. Conclusion

Building an MTG rules engine is a substantial undertaking that requires:

1. **Deep rules knowledge** - The 292-page Comprehensive Rules must be thoroughly understood
2. **Careful architecture** - Event sourcing and immutable state recommended for debugging and replays
3. **Incremental approach** - Start with core mechanics, add cards gradually
4. **Extensive testing** - Every card interaction is a potential bug
5. **Maintenance commitment** - New cards release every few months

The existing open-source implementations (Forge, XMage) represent decades of combined effort and millions of lines of code. A new implementation should leverage their learnings while potentially improving on architecture (modern language, better separation of concerns) or user experience.

---

## Sources

**MTG Rules:**
- [MTG Wiki - Comprehensive Rules](https://mtg.fandom.com/wiki/Comprehensive_Rules)
- [Official Wizards Rules Page](https://magic.wizards.com/en/rules)
- [Yawgatog Hyperlinked Rules](https://yawgatog.com/resources/magic-rules/)
- [MTG Wiki - Layers](https://mtg.fandom.com/wiki/Layer)
- [MTG Wiki - State-Based Actions](https://mtg.fandom.com/wiki/State-based_action)
- [Draftsim - MTG Priority](https://draftsim.com/mtg-priority/)
- [Draftsim - MTG Zones](https://draftsim.com/zones-mtg/)
- [Draftsim - MTG Phases](https://draftsim.com/mtg-phases/)
- [Draftsim - MTG Layers](https://draftsim.com/mtg-layers/)
- [Card Kingdom - Priority and Stack](https://blog.cardkingdom.com/essential-mtg-definitions-priority-and-the-stack/)

**Open Source Implementations:**
- [Forge GitHub Repository](https://github.com/Card-Forge/forge)
- [Forge Card Scripting API](https://github.com/Card-Forge/forge/wiki/Card-scripting-API)
- [XMage GitHub Repository](https://github.com/magefree/mage)
- [XMage Architecture Analysis (Delft)](https://delftswa.gitbooks.io/desosa2018/content/xmage/chapter.html)
- [Cockatrice GitHub Repository](https://github.com/Cockatrice/Cockatrice)
- [CGomesu - Forge and XMage Comparison](https://cgomesu.com/blog/forge-xmage-mtg/)

**MTG Arena:**
- [MTG Arena Rules Engine Article](https://magic.wizards.com/en/news/mtg-arena/on-whiteboards-naps-and-living-breakthrough)
- [Popular Science - MTG Arena Rules Engine](https://www.popsci.com/story/technology/magic-arena-rules-engine/)

**Complexity and Card Count:**
- [Draftsim - How Many MTG Cards](https://draftsim.com/how-many-mtg-cards-are-there/)
- [Draftsim - MTG Complexity Creep](https://draftsim.com/mtg-complexity-creep/)
- [Kotaku - MTG Computational Complexity](https://kotaku.com/magic-the-gathering-is-so-complex-it-could-stump-a-com-1834623872)

**Modern Implementations:**
- [MTG-Paradox-Engine (TypeScript)](https://github.com/MTG-Paradox-Engine/mtg-paradox-engine)
- [Rust Forum - Card Game Rules Engine Discussion](https://users.rust-lang.org/t/architecture-discussion-writing-a-card-game-rules-engine-in-rust/41569)
