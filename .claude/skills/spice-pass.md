# Spice Pass: How to Inject Format-Defining Cards into a Custom Set

> Companion to `implement-mtg-cards.md`. That doc covers the *mechanics* of
> wiring a card. This doc covers the *design* of cards that warp formats —
> the deliberately strong, deliberately interesting "spice" picks that take
> a vanilla custom set and make it feel like real Magic.

## When to use this

A custom set is "vanilla" when 75–85% of its creatures are stat-line-only or
have a single boring ETB trigger. The cards work, but no card *defines* the
format. Every game plays the same shape. Open a spice pass when you want a
set's archetypes to feel real — when a deckbuilder should look at the set
and say "I could build around X" or "X plus Y goes infinite."

The Star Wars pilot took the set from 275 → 289 cards (15 spice picks) and
moved it from "untested" to a 60% win rate in the Wave-22 tournament — the
Modern-staple tier the plan targeted. Dragon Ball followed at 217 → 225
(8 spice picks).

## The 10 broken-card patterns

Cards that warp formats almost always exhibit one or more of these. Mark
Rosewater's design lessons + the Draftsim broken-card taxonomy converge on
this list. **Every spice card should target 1–3 patterns.**

1. **Disproportionate efficiency** — outsized impact per mana (Ragavan: 4
   abilities at `{R}`)
2. **Hard to interact with** — protection, ward, hexproof, indestructible,
   "shroud until your next turn" (The One Ring)
3. **Snowball value engine** — each turn does more than the last
   (planeswalkers, Sheoldred, Up the Beanstalk)
4. **Compression / threat-and-answer** — multiple modes or abilities on one
   card (Bonecrusher Giant, Snapcaster Mage, Fable of the Mirror-Breaker)
5. **Asymmetric prison** — affects opponents more than you (Blood Moon,
   Chalice of the Void, Stony Silence)
6. **Free / alternative cost** — pitch costs, cast-from-graveyard,
   cast-from-exile, cascade
7. **Tutoring & consistency** — find the exact right card (Demonic Tutor,
   Stoneforge Mystic)
8. **Recursion / persistence** — graveyard as second hand (Bloodghast,
   Underworld Breach, Reanimate)
9. **Tempo theft** — extra turns, extra combats, time walk
10. **Two-card combo enablement** — explicit infinite/oppressive synergy
    with one specific other card (Splinter Twin + Pestermite)

## Process loop

1. **Pilot one set.** Don't try to roll across the whole project at once.
   Pick a set whose flavor matches the broken-on-purpose ethos — anime
   power-spike narratives (Saiyan transformations, Force users) work
   beautifully.
2. **Survey the set.** Read the file once. Note the existing factions
   (subtype clusters) — they're your archetype anchors. Note which legends
   already exist; you'll likely add new variants ("Boba Fett, Hunter of
   Hunters" alongside the existing "Boba Fett, Bounty Hunter").
3. **Synthesize the design.** Use `Plan` subagent to propose 12–15 spice
   picks across rarities. Feed it the 10-pattern taxonomy and the engine
   capability list. The agent writes the design doc; you implement.
4. **Map to engine.** For each card, identify the helpers and events
   needed. Sort into phases (see below).
5. **Implement Phase A first.** Within-engine cards only. Get a green
   commit. Each card needs a positive-path test and at least one edge
   case.
6. **Spawn a code reviewer.** Background `general-purpose` subagent. The
   reviewer catches subtle bugs (wrong payload key, missing source
   filter, infinite-trigger loops).
7. **Fix reviewer findings, re-test, commit Phase B-1.** Add small engine
   extensions if needed.
8. **Run a tournament.** Validate the balance shift in real play.
9. **Iterate.** Phase B-2 (complex), Phase B-3 (parked until engine
   catches up).

## Phase organization

**Phase A** — within current engine. No new helpers. Aim for 6–10 cards
covering compression, tutoring, recursion, equipment, simple triggers.
Easy to test, easy to ship.

**Phase B-1** — small engine extensions (≤30 lines each). Examples we
shipped on this project:

- `subtypes_any: list[str]` filter on `SEARCH_LIBRARY`
- `was_destroyed_this_turn(obj_id, state)` helper + lazy system tracker
- `condition_fn` parameter on `make_cost_reduction`
- `precondition_fn` parameter on `make_activated_ability`

Pattern: each extension is broadly useful (not just for one card) and
ships with at least one test. Document in the extension itself why it
exists.

**Phase B-2** — complex but possible on existing engine. Sagas, multi-stage
triggers, stack-aware costs. May require simplification vs the printed
text.

**Phase B-3** — deferred until engine gaps close. Modal multi-choice
prompts (vs heuristic-picked), full DFC/transform with separate back-face
CardDefinitions, persistent copy-creature, full Adventure split-cost.
Spawn the design but mark "needs engine X."

## Engine surface map (as of W12)

### Helpers shipped you'll lean on

| Helper | Use |
|---|---|
| `make_etb_trigger(obj, effect_fn, filter_fn=...)` | "When this enters, do X." Custom `filter_fn` lets you trigger on *another* permanent's ETB. |
| `make_attack_trigger(obj, effect_fn)` | "Whenever this attacks, do X." |
| `make_damage_trigger(obj, effect_fn, combat_only=True)` | Combat-damage-to-player triggers (Ragavan-shape). |
| `make_death_trigger(obj, effect_fn, filter_fn=...)` | Self-death or filtered by `filter_fn` for "another X dies" triggers. |
| `make_keyword_grant(obj, ['flying', 'haste'], affects_self)` | **Self-keyword grant**. Many existing cards have keywords *only* in flavor text — wire them. |
| `make_static_pt_boost(obj, +X, +Y, filter_fn)` | Lord effects. Conditional gating via `filter_fn`. |
| `make_cost_reduction(obj, applies_to, amount, condition_fn=...)` | Spell-cast cost reduction. `condition_fn` gates on game state. |
| `make_ward(obj, mana_cost="{2}")` | Ward — counter target spell unless paid. |
| `make_equipment_setup(power_mod, toughness_mod, keywords, equip_cost, subtypes_to_add)` | Equipment auto-attach. `subtypes_to_add` adds creature-side subtypes (Sword, Mount). |
| `make_activated_ability(obj, cost, effect_fn, precondition_fn=...)` | Activated abilities. Costs are comma-separated. `precondition_fn` gates legality before cost-pay. |
| `make_replacement_effect(obj, event_filter, replace_fn, duration='end_of_turn')` | "If X would happen, Y instead." General framework (W1). |
| `make_castable_from_zone(obj, target_card_id, zone, cost_modifier)` | Cast from graveyard / exile / library top (W7). |
| `make_saga_setup(obj, {1: ch_i, 2: ch_ii, 3: ch_iii})` | Saga chapter dispatcher. Sacrifice-after-final-chapter is automatic. |
| `make_modal_etb_trigger(obj, modes, min_modes, max_modes)` | Modal ETB choice. |
| `make_spree_setup(obj, base_modes, ...)` | Spree-style cost-per-mode (W12). |
| `was_destroyed_this_turn(obj_id, state)` | Per-turn destruction tracker. Lazy-installs. |
| `threaten_creature(target_id, new_controller, source_id)` | "Gain control + untap + haste EOT" — returns events. |

### Events worth knowing

`EXILE_TOP_PLAY` (Boba/R2 cascade-style), `CREATE_TOKEN` (Treasure
shape: `{'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}`),
`SEARCH_LIBRARY` (with `subtypes_any` for "Jedi or Sith" tutors),
`RETURN_FROM_GRAVEYARD`, `EXTRA_TURN`, `EXTRA_COMBAT`, `GRANT_KEYWORD`,
`PT_MODIFICATION`, `TRANSFORM` (mutates an object's characteristics
in-place — power, toughness, name, subtypes, types).

### Patterns the engine still struggles with (as of W12)

- **Detecting which alt-cost was paid** — Boba dash style, where the
  game needs to know "did this cast use the alternate cost so I can
  schedule the EOT bounce." Skip dash mechanics until cast-tracking
  surfaces the cost paid.
- **Player-targeting hexproof** — "you have hexproof until your next
  turn" requires a player-targeting replacement framework. Card-targeting
  ward is fully supported.
- **Modal multi-choice triggered abilities** — `make_modal_etb_trigger`
  exists for ETB; for *upkeep* modals, write a custom upkeep trigger
  that picks via heuristic until the prompt-driven version lands.
- **Auto-attach after multi-search** — Saga chapter III "tutor a
  Lightsaber and a Jedi, attach them" needs both searches to resolve
  before the ATTACH event. Defer auto-attach for v1.

## Common gotchas (real bugs we hit)

1. **Self-keyword grants are filter-based.** Use `make_keyword_grant(obj, ['flying'], lambda t, s: t.id == obj.id)`. The flavor text "Flying, haste" alone doesn't wire those keywords on most existing cards.

2. **Treasure tokens use the `'token'` payload key.**
   ```python
   Event(type=EventType.CREATE_TOKEN, payload={
       'controller': obj.controller,
       'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}},
   }, source=obj.id)
   ```

3. **`EXILE_TOP_PLAY` payload uses `caster`, not `controller`.** The handler reads `event.payload.get('caster')` to grant play-permission. If you write `'controller': obj.controller`, the play-permission lands on the *defender* whose library was exiled.

4. **Activated cost format must be comma-separated.** `"{4}{T}"` doesn't parse `{T}` — the cost goes through as a generic-mana sequence. Write `"{4}, {T}, Sacrifice this artifact"`.

5. **`SACRIFICE` is rewritten to `ZONE_CHANGE` in the TRANSFORM phase.** A system-level interceptor in `game.py` converts `SACRIFICE` to `ZONE_CHANGE` with `payload['reason'] == 'sacrifice'` before REACT runs. To listen for "whenever you sacrifice a Treasure," filter on `ZONE_CHANGE` with `reason == 'sacrifice'`, not `SACRIFICE`.

6. **Tokens minted via `CREATE_TOKEN` don't fire `ZONE_CHANGE` or `OBJECT_CREATED`.** The handler builds the token and writes its id back into the `CREATE_TOKEN` event's `payload['object_id']`. So a "whenever another Droid enters" filter that only catches `ZONE_CHANGE` will miss token Droids. Add `EventType.CREATE_TOKEN` to the filter — and **exclude `event.source == src.id`** to avoid infinite loops on your own emitted tokens.

7. **`pending_choice` is singular.** `state.pending_choice` (single PendingChoice), not `pending_choices`.

8. **`make_upkeep_trigger` filters on `state.active_player`, not the event payload.** Tests must `game.state.active_player = p1.id` before emitting `PHASE_START`. The payload's `active_player` field is informational; the trigger ignores it.

9. **`ManaCost` exposes `mana_value` (property), not `total_cost()`.** Same for `is_free`, `colors`, `to_string`.

10. **Library search filter requires `obj.card_def is not None`.** Tests that synthesize library cards directly via `create_object` must pass a real `card_def`, not just `Characteristics`. Otherwise the filter rejects every candidate and the search opens an empty choice (returns None).

11. **`ObjectState` has no `flags` dict.** For ad-hoc per-object state, use `setattr(obj.state, '_my_flag', True)` and `getattr(obj.state, '_my_flag', False)`. Pick a name unlikely to collide with future engine fields.

12. **AI scoring penalises bare-keyword text.** `_is_removal_like` matches `"exile"`, `"destroy"`, `"damage"`. Flashback's reminder "(...Then exile it.)" trips it, then the no-targets path slaps a -3.0 risk penalty. Either tighten the heuristic (we did: phrase-match `"exile target"` etc., strip parentheticals) or write your card text to avoid bare keywords in flavor.

## Testing patterns

Mirror `tests/test_star_wars_spice.py` shape. The standard helper:

```python
def _put_on_battlefield(game, player, card_name):
    card_def = STAR_WARS_CARDS[card_name]
    obj = game.create_object(
        name=card_name, owner_id=player.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=None,  # IMPORTANT: don't pass card_def to create_object
    )
    obj.card_def = card_def  # set after creation
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'from_zone': f'hand_{player.id}',
                 'to_zone': 'battlefield', 'to_zone_type': ZoneType.BATTLEFIELD},
    ))
    return obj
```

Why `card_def=None` then assign after: `create_object` runs
`setup_interceptors` for BATTLEFIELD/COMMAND zones. Putting the card in
HAND first with no `card_def` skips that, then the ZONE_CHANGE to
battlefield runs setup exactly once (the correct path).

For each card write:

- **Load test** — card def loads, expected types/subtypes/supertypes,
  expected interceptor count.
- **Positive-path trigger test** — fire the trigger, assert the right
  events emit in `game.state.event_log`.
- **At least one edge case** — opp upkeep doesn't fire your upkeep; own
  ETB doesn't self-trigger an "another X enters" ability; empty library
  doesn't crash; non-matching subtype is rejected.

For activated abilities with `precondition_fn`, test both branches: gate
False → ability not legal; gate True → legal.

For saga chapters, mirror `tests/test_saga.py`. Force chapter advancement
by emitting `PHASE_START` with `phase='draw'` after setting
`state.active_player`.

## Balance validation: tournament protocol

```bash
python scripts/play/custom_set_tournament.py \
    --games 3 --max-turns 14 --difficulty hard \
    --sets "GHB,NRT,SPMC,MHA,LTR,PKH,ZLD,OPC,JJK,FINC,DMS,SWR" \
    --out logs/tournament_w22_spice.json \
    --report logs/tournament_w22_spice_report.txt \
    --seed 42 --workers 4
```

**Reading the report:**

- A spiced set in the **55–65% WR** band hits Modern-staple tier — what
  you usually want for a mixed-by-rarity pass.
- **70%+ WR** means a single card (or stack of cards) is too strong.
  Pick the highest-cast-rate spice card and power it down (cost +1, P/T
  -1, or remove a clause).
- A high **error count** for the spiced set is usually **timeouts**, not
  crashes. The spice extends games via attrition / value engines /
  recursion. Re-run with `--max-turns 25` to confirm; that's the
  format-warping signal you wanted.

If the spiced set drops below 50%, the AI isn't playing the spice cards
right. Check `_is_removal_like` and similar heuristics for false
positives in your card text.

## Subagent playbook

| Task | Subagent | When |
|---|---|---|
| Design 12–15 spice picks for a set | `Plan` (background) | Once per set, before implementation |
| Code review after Phase A or B-1 | `general-purpose` (background) | After tests green, before commit |
| Survey new engine surface (after parallel agent merges Wn) | `Explore` (foreground) | When you need to know what API is available |
| Run tournament | `Bash run_in_background` | Each phase commit |

**Pattern**: spawn the slow background work (DBZ design, code review, tournament run) and use the wait time for the foreground work (the next set's Phase A, fixing reviewer findings on the previous phase). Avoid spawning more than 2–3 background agents at once — coordination cost grows faster than throughput.

## Per-card checklist

Before a card commit:

- [ ] Card name doesn't collide with an existing card in the set
  (e.g. `BOBA_FETT` already existed; mine is `BOBA_FETT_HUNTER_OF_HUNTERS`)
- [ ] Self-keywords wired via `make_keyword_grant` (don't rely on flavor
  text)
- [ ] If using `make_etb_trigger` with a custom filter, check both
  `ZONE_CHANGE` and `OBJECT_CREATED` (and `CREATE_TOKEN` for token
  detection)
- [ ] If reacting to sacrifice, listen on `ZONE_CHANGE` with
  `reason == 'sacrifice'`, not `SACRIFICE`
- [ ] Activated ability cost format: comma-separated; sacrifice is part
  of the *cost*, not the *effect*
- [ ] EXILE_TOP_PLAY uses `caster` key
- [ ] Card added to both the registry dict and the `CARDS` list
- [ ] Smoke test: `python -c "from src.cards.custom.<set> import NEW_CARD"`
- [ ] Unit test: positive path + 1 edge case
- [ ] Full suite green: `python -m pytest tests/ -q`
- [ ] Reviewer flagged nothing high-severity (or those flags are fixed)

## Phase commit shape

Each phase commit should answer: *what cards, what new engine, what's
deferred, what's the test count, what does the suite look like.* Pattern:

```
feat(spice): <set> Phase <X> — <one-line summary>

<Why this phase exists / what triggered it>

Cards (N):
- <card>: <one-line role>
- ...

Engine extensions (M, all broadly useful):
- <name>: <purpose>

Approximations vs the original design:
- <thing simplified>: <why>

Tests: <new count> (was <old>). Coverage: <what>.
Suite: <total> passing. Pre-existing failures: <count>.

Plan reference: .claude/plans/<plan>.md (Phase X section).
```

This shape makes future-you (or a future agent) able to read the git log
and understand the spice trajectory without opening every file.

## What's worth saving as memory vs not

**Save**: which sets have been spiced, with rough power tier from the
tournament. Future agents picking the next pilot need this.

**Don't save**: card-level rules text or specific helper signatures —
those rot fast. Read the file.

**Save**: gotchas that bit you (caster vs controller, `mana_value`
property, ObjectState has no `flags` dict). Future agents will hit the
same ones.

## Worked example — Star Wars trajectory

For reference, the SW pilot's full arc:

| Phase | Cards | Engine |
|---|---|---|
| A | Boba Fett HoH, IG-88, Yoda Living Force, Bossk, Han Solo HP, Holocron, Beskar, Sith Resurgence | `subtypes_any` |
| B-1 | Kylo Ren, Stormtrooper Patrol, R2-D2, Vader | `was_destroyed_this_turn`, `condition_fn`, `precondition_fn` |
| B-2 | The Force Itself (saga) | (uses W1 replacement) |
| B-3 | Luke Last Jedi, Princess Leia | (uses W12 modal, in-place TRANSFORM) |

Set: 275 → 289 cards. Tests: 0 → 50. Tournament: 60% WR (Modern-staple
tier confirmed). Same shape repeats for any set.
