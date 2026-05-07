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

## The 11 broken-card patterns

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
11. **Build-around / synergy-dependent** — vanilla in a generic deck,
    devastating when the deck is built around it (Tifa Lockheart doubles
    power on landfall, Sazh's Chocobo grows with each landfall, EOE
    Hydras scale with Discover, Companion-style "if your deck contains
    only X" mythics). The card *needs* its support to shine — and that
    is the point. **This is the pattern most likely to fail tournament
    measurement** because generic deckbuilders won't include the support
    package, so a build-around card looks weak in average play.

## Capability test as the design gate

Tournament winrate is **not** a useful signal for build-around mythics
(pattern 11). The Wave-22 R5 PKH spice pass shipped 8 cards and tournament
winrate moved from 25% → 27.8% (within ±7pp noise). When we ran the
capability test (each card placed in a hand-curated synergy deck, played
vs the set's generic baseline), **5 of 8 cards never even entered the
deck** because the generic builder filtered them by CMC. The 3 that did
enter cast at 0.03–0.10. The set looked stable in the tournament because
support cards carried the wins; the spice cards were passengers.

Every spice card now must pass the capability test before commit:

```
python scripts/play/capability_test.py --set <CODE> --card "<NAME>" --games 10
```

It builds a 60-card synergy deck (4 of focal + 2 of each partner from
`<set>_synergies.py` + filler + 24 lands), plays it vs the generic
baseline, and reports:

- **focal cast/game** — in how many games does the focal land at least
  once? (With focal-in-opener stacking enabled by default, only 1 of 4
  deck copies is forced to the top — `cast/copy` is capped at 0.25 even
  in perfect play, so `cast/game` is the natural unit.)
- **focal win-rate-when-in-play** — for permanents (creatures, equipment,
  enchantments), the rate at which the focal is on the battlefield at
  game end on the winning side.
- **capability_score** = cast/game × win-correlation. **Threshold ≥ 0.30**.

The win-correlation differs by card type:
- **Permanents**: WR-in-play (the focal is on the board at game end and
  the deck won)
- **One-shot spells (sorceries / instants without a creature side)**:
  `synergy_deck_winrate` (the deck's overall winrate). Sorceries always
  go to graveyard after resolving so WR-in-play would always be 0% — the
  deck-winrate substitution is correct.

A passing card means: in its supported deck, the focal lands in 30%+ of
games AND the deck wins. A failing card needs redesign (usually: cheaper
cost so it actually casts in 14-turn games, or a chain trigger that scales
with the synergy package instead of a standalone effect).

### Methodology — why focal-in-opener

Without stacking the focal into the opening hand, you measure two things
at once: "did the card get drawn?" and "did the deck win when it did?"
Draw variance dominates the signal at small sample sizes. The right
question for build-around testing is the second one alone — *given* the
card lands, does it carry?

The harness implements this via a `pre_start_hook` on `play_one_game`
that moves a focal copy to the top of p1's library after shuffle. It's
on by default; pass `--no-focal-in-opener` to opt out for a "natural
draw" variance experiment. Real MTG playtesting follows the same
convention — when you're testing whether a card is good, you stack the
deck so the card is in your opening hand.

## Synergy package convention

For each spice card, declare 8–12 partner card names in the set's
`<set>_synergies.py`. Partners should be cards that already exist in the
set and whose presence makes the focal substantially better. Examples
from PKH:

- **Charizard, Mega Evolved** (snowballs +1/+0 + ping per red spell cast)
  → Flamethrower, Fire Blast, Overheat, Vulpix, Charmander, Slugma, Numel,
  Torchic, Cyndaquil, Litten, Ponyta. Without these, Charizard is a
  vanilla 3/3 flier; with them, the deck's natural plays grow it into a
  finisher every turn.
- **Master Ball, Catcher Engine** (haste to every cheap creature you cast)
  → Charizard Mega, Moltres Phoenix, Magmortar, Blaziken, Infernape,
  Rapidash, Magmar, Hitmonchan, Lucario, Primeape — strong tutoring
  targets.

Naming convention: registry maps focal card name → list of partner names.
The capability harness validates every partner exists in the set's pool
(catches typos at import time).

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

13. **`ATTACH` payload uses `object_id` / `target_id` — not `source` / `target` and not `equipment_id`.** The canonical event is `Event(type=EventType.ATTACH, payload={'object_id': equipment.id, 'target_id': creature.id}, source=equipment.id)`. The subtypes-add listener (`_make_attached_subtypes_listener`, used by `make_equipment_setup(subtypes_to_add=...)`) filters on `payload['object_id']`. Tests that emit a fake ATTACH with `{'source': ..., 'target': ...}` will silently no-op for any equipment-static built through `make_equipment_setup` — the test passes the load check and fails the behavior check. Independent: some card-side triggers in the wild (e.g. DBZ's Trunks) read `payload.get('target')` directly via custom filters; if you copy that pattern blindly into a test for an `make_equipment_setup` card, you'll get a false-passing test. Always use the canonical keys.

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

## Lessons from PKH v1 → v2 (the build-around pivot)

The Pokemon Horizons spice pass exposed two methodology gaps the prior
sets didn't surface:

1. **Standalone effects don't show up as spice in the tournament.**
   v1 PKH shipped 8 cards with effects like "ETB deal 4 damage", "draw
   on combat damage", "{R} less if 4 cards in graveyard." Each card was
   a standalone power play. Tournament moved 25% → 27.8% (within noise).
   Capability test revealed: 5 of 8 cards never made the deck because
   the generic builder filtered MV4+ mythics. The 3 that did made the
   deck cast at 0.03–0.10 — they weren't carrying their decks.

2. **Tournament winrate is the wrong gate for build-around mythics.**
   Cards with pattern 11 (build-around) need their support package to
   shine. Generic deckbuilders don't include the support, so the card
   looks weak in tournament play even when it's actually format-defining
   in its proper deck. Capability test (per-card, in a hand-curated
   synergy deck) is the right gate.

The v2 redesign:

- Lowered CMCs across the board (Charizard {2}{R}{R} → {2}{R}, Reshiram
  {4}{R}{R} → {3}{R}{R}, Hyper Beam {2}{R}{R} → {1}{R}, etc.) so cards
  actually cast in 14-turn games.
- Replaced standalone effects with chain/snowball/scaling triggers —
  Charizard pumps + pings on each red spell cast, Pikachu grows on each
  player damage, Reshiram's ETB damage scales with creatures in your
  graveyard.
- Equipment with manual `equip {1}` activation didn't fire (AI doesn't
  use it well) — moved Volcanic Mantle to a Legendary Enchantment with
  an auto-firing global "+1/+1 + trample on attack" trigger.
- A real bug surfaced: Hyper Beam's `resolve(spell, state, targets)`
  signature crashed every cast — engine contract is `resolve(targets,
  state)`. Capability test caught what the unit tests didn't.

Apply this to future spice passes: target pattern 11 explicitly when
you want a "build-around mythic" feel. Always run the capability test
before committing the card.

### v3.5 — methodology refinements

The v2 redesign + capability test cycle exposed two more measurement
gaps. Fixed in v3.5 (commit `fbbb459` and `1a45ce8`):

1. **Engine targeting passes `[[Target(...)]]` for single-target spells.**
   The resolve function gets a double-nested list, not a single Target.
   Spells (Hyper Beam) crashed every cast with "TypeError: unhashable
   type: 'list'". The defensive resolve pattern now is:

   ```python
   def resolve(targets, state):
       if not targets:
           return []
       t = targets[0]
       if isinstance(t, list):       # double-nested wrapper
           t = t[0] if t else None
       if t is None:
           return []
       if isinstance(t, str):
           target_id = t
       elif hasattr(t, 'object_id'): # older test stubs
           target_id = t.object_id
       elif hasattr(t, 'id'):        # real Target dataclass
           target_id = t.id
       ```

   `sith_resurgence_resolve` and any other custom-set resolve function
   have the same latent bug if they use the simple `targets[0].object_id
   if hasattr(targets[0], 'object_id') else targets[0]` pattern. Fix
   them when you trip them.

2. **Cast/copy was the wrong metric for build-around testing.** With
   focal-in-opener stacking 1 copy and 4 in the deck, cast/copy ceiling
   is 0.25 — the threshold of 0.30 was numerically unreachable. v3.5
   switched to cast/game (ceiling 1.0+ per game) which is the natural
   unit. The threshold of 0.30 means roughly "lands in 30%+ of games."

3. **WR-in-play is meaningless for sorceries.** They go to graveyard
   immediately after resolving, so the "permanent on the board at game
   end" measurement always gives 0%. The sorcery-aware metric uses
   `synergy_deck_winrate` for non-permanents instead — captures "did
   the deck win in games where the spell was cast" without requiring
   the spell to persist.

After these fixes: PKH redesigned v2 cards moved from **0/8 PASS** under
the v2 metric to **6/8 PASS** under v3.5 — same cards, same redesign,
just measured correctly.

## Cross-engine port: Minecraft TCG

A second port (after PKH/MTG) tested whether the methodology generalizes
to a fundamentally different engine. Minecraft TCG has its own engine —
materials economy (5 resources: wood/stone/iron/redstone/diamond instead
of mana), 3x3 build grid, biome-mining loop, avatar+gear instead of life
total, and direct-resolve combat with no stack. Six spice candidates
(Ender Dragon, Wither, Iron Golem, Ravager, Elder Guardian, Blaze) all
started as either vanilla bosses or weak triggers.

What ported cleanly:

- **Capability test gate** — same shape (synergy deck × baseline × N
  games, focal-in-opener stacking, capability_score = cast/game ×
  win-correlation). The MC harness lives at
  `scripts/play/minecraft_capability_test.py` and is structurally
  identical to the MTG version.
- **Synergy registry pattern** — `src/cards/minecraft/synergies.py` maps
  focal → partner names from the same set. Per-set registry stays
  hand-curated; partners must exist in the set.
- **Build-around redesign template** — replacing standalone effects
  with environment-dependent triggers (worker-count payoff, hostile-count
  payoff, diamond-investment payoff, block-destruction payoff) made every
  card noticeably more interesting AND moved the capability score.
- **Sorcery-aware metric** — Minecraft Action cards resolve directly to
  graveyard (no battlefield persistence). `is_action_card()` flips the
  metric to deck-winrate. Same gotcha as MTG sorceries.
- **Missing engine hooks surface** — to wire EG (mining payoff) and
  Ravager (block-destruction payoff), I added a generic `mc_on_event`
  hook to the system interceptor. PKH had no equivalent need; in MTG
  the interceptor system is the primary surface. Slow-economy engines
  with bespoke event types may need one engine extension per spice pass.

What did NOT port cleanly:

1. **The 0.30 threshold is calibrated for MTG-speed economies and is
   too high for slow-ramp engines.** MC's economy is ~1 material per
   turn (avatar mining), with premium materials (redstone, diamond)
   gated behind action cards. Cards costing 3+ materials cap their cast
   rate around cast/game = 0.30-0.50 even with focal-in-opener and a
   hand-tuned ramp package. After the v9 sweep:

   | Card | Score | Cast/g | WinCorr | Pass(0.30) |
   |---|---|---|---|---|
   | Elder Guardian | 1.26 | 1.31 | 0.96 | YES |
   | Iron Golem | 0.33 | 0.46 | 0.67 | YES |
   | Wither | 0.33 | 0.41 | 0.80 | YES |
   | Ravager | 0.26 | 0.44 | 0.60 | borderline |
   | Blaze | 0.27 | 0.31 | 0.86 | borderline |
   | Ender Dragon | 0.16 | 0.31 | 0.50 | no |

   v1 baseline was **1/6 PASS**. v9 is **2-3/6 stable PASS** with all
   six producing positive capability signal. The redesign methodology
   reliably moved the score; the threshold is the ill-calibrated knob.
   Engines with slower economies need lower thresholds (~0.20) or longer
   game horizons (max_turns=35-40 instead of 20-25).

2. **Cast rate and win-correlation can decouple in slow engines.** PKH
   cards that cast tended to also win. In MC, several cards (Iron Golem
   at cast 0.46/win 0.67, Wither at 0.41/0.80) cast reliably but their
   build-around payoff isn't game-winning even when triggered. ETB
   damage scaling that worked in MTG (deal `N` for each match) often
   needs `2*N` or `3*N` in MC because avatar HP is 20 with armor
   reduction and games run longer per damage point.

3. **Synergy decks must include explicit ramp tied to the focal cost.**
   The v2 MC synergies were "thematic" (Iron Golem ↔ Workers) without
   accounting for material economics. v3 added Strip Mine (the only
   cheap redstone path) to every redstone-focal package. Cast rate
   tripled. Lesson: register the focal's *cost-supporting cards*, not
   just its *effect-supporting cards*.

Engine-extension cost for the port:

- Added `mc_on_event(obj, state, event)` hook to
  `register_minecraft_system_interceptors`. Generic per-event listener;
  fires for every MC battlefield card whose `card_def.mc_on_event` is
  callable. ~25 lines, opens the door for any "react to X" trigger.
- Added `MC_MATERIAL_SPEND` and `MC_MATERIAL_GAIN` to the cleanup_filter
  set. The spend event already existed but wasn't `game.emit()`-ed —
  patched `play_card` to emit it through the pipeline.

For the next port: budget one small engine extension per pass. The
hook surface that the existing cards use is rarely the hook surface
that build-around cards need.

### Audit the AI for meta-awareness BEFORE running capability tests

The v9 MC sweep (above) measured cards while the AI was playing badly —
it scored Action cards at flat `+8` (lowest priority), so it ignored
Strip Mine, Explore Map, Find Diamonds, and the entire ramp toolkit.
The AI's mining heuristic also went diamond → redstone → iron → stone
→ wood, which means it never mined Forest first turn, which means it
never had wood to play workers or Explore Map turn 2.

**The MC meta is**: explore biomes for permanent +1 yield (1 wood for
Old Growth Forest = 2 W/turn forever), deploy Workers ASAP for
compounding economy, then build turn-bonus structures, then deploy
bombs. The AI was playing none of that. Capability scores were
measuring AI ineptitude, not card capability.

After v10-v12 AI fixes (meta-aware `_choose_card_to_play` with phase
bonuses + wood-first mining when Explore Map / Workers are pending),
PASS rate went **1/6 (v1 vanilla) → 2/6 (v9, broken AI) → 3/6 (v12,
meta-aware AI)** with no card changes between v9 and v12.

| Card | v9 (broken AI) | v12 (meta-aware AI) |
|---|---|---|
| Elder Guardian | **1.26** | **0.92** |
| Iron Golem | 0.31 | **0.44** |
| Wither | 0.33 | 0.00 |
| Ender Dragon | 0.16 | 0.12 |
| Ravager | 0.26 | 0.17 |
| Blaze | 0.27 | **0.31** |

Note that EG and Wither *regressed* with the smarter AI — they
got cast slightly less often because the AI was now spending early
turns ramping. That's the right tradeoff: the meta-aware AI is
playing the actual format, and cards that PASS under those conditions
are robustly format-defining.

**Lesson for any new engine port**: before trusting capability scores,
manually verify that the AI plays the format meta. A heuristic AI
optimized for a generic "play the biggest thing affordable" isn't
testing build-around cards; it's testing whether the build-around
*happens to align with* "biggest thing." Audit:

1. Read the AI's card-scoring function. Does it weight ramp and engine
   pieces above mid-cost mobs? Does it favor incremental advantage
   over face-value stat lines?
2. Read the AI's resource-acquisition heuristic (mining, mana ramp,
   draw, etc.). Does it match the format's optimal early game?
3. Watch one game manually. Is the AI playing the meta or stalling
   into raw value?

If the AI plays the meta poorly, the capability test measures AI
weakness instead of card weakness. Fix the AI first.

### Discovering the meta when you don't know it yet

The MC story above had a luxury: the user *told* us the meta
("explore biomes, deploy workers, upgrade generation"). For a brand
new engine you've just built, nobody knows the meta yet — the whole
point of playtesting is to find out. The chicken-and-egg problem:
you can't audit the AI for meta-awareness if you don't know the
meta. And you can't run capability tests on a non-meta-aware AI.

The fix: a **variant tournament** that finds the meta by self-play.
Defined a small set of named "biases" (each is a parameter preset
for the engine's AI), run them in a round-robin, see which bias
wins. The winning bias *is* the format's tentative meta.

Harness lives at `scripts/play/variant_tournament.py`. It dispatches
across engines (MTG and MC at v1; new engines plug into the
`ENGINES` registry). Default MC variants: `balanced`, `aggro`,
`ramp`, `explore`, `workers`, `random`, `largest`. The `random` and
`largest` variants are deliberate baselines — anything that doesn't
beat them in head-to-head isn't a real strategy.

Real example output (MC, 7 variants × 3 starter decks × 2 games per
pair = 126 games):

```
              balanced  aggro    ramp  explore workers  random largest
balanced            --   0.17    0.33    0.50    0.17    0.50    0.00
aggro             0.50    --     0.17    0.17    0.17    0.17    0.17
ramp              0.33   0.33     --     0.17    0.50    0.33    0.00
explore           0.17   0.33    0.33     --     0.00    0.17    0.00
workers           0.50   0.50    0.33    0.33     --     0.50    0.33
random            0.33   0.50    0.33    0.67    0.17     --     0.33
largest           0.33   0.17    0.17    0.33    0.17    0.17     --

OVERALL RANKING
1. workers       41.7%
2. random        38.9%
3. balanced      27.8%  ramp 27.8%
5. aggro         22.2%  largest 22.2%
7. explore       16.7%
```

The harness identified `workers` (deploy Workers ASAP) as the meta —
exactly matching the human-described meta from the prior section.
That's the win condition for this approach: the harness rediscovered
without prior the strategy a human would have hand-tuned.

**Recommended workflow for porting to a new engine:**

1. **Build a parametrized AI** — score-based with named bias presets.
   For each design axis you suspect matters (aggression, ramp, draw,
   tribal, etc.), define a preset that turns that axis up.
2. **Always include `random` and `largest` as baselines.** If your
   "real" strategies don't beat random by ≥5%, your variant set
   isn't expressing meaningful differences yet — go define more
   axes.
3. **Run a small variant tournament** (`--games 2-4`, all default
   decks). Total game count ≈ C(V,2) × D × 2N = manageable.
4. **Read the discovered meta.** The winning variant tells you the
   AI tuning + capability-deck tuning to lean into.
5. **Tune the default AI** (the "balanced" preset) toward the
   winner's bias. Re-run the tournament to confirm balanced still
   wins or ties top variants.
6. **Now run capability tests.** Build-around scores measured against
   a meta-tuned AI are the real signal.

This puts the variant tournament BEFORE capability tests in the
spice-pass workflow for new engines. For engines where the meta is
known and the AI already plays it well (MTG today), skip step 1-5
and go straight to capability tests.

### "Do more of what worked"

Once a variant wins, the natural next step is to push that bias
further. Two ways to amplify:

- **Code:** crank the winning preset's bonuses up another 50-100%
  and re-run the tournament. If it still wins, the format genuinely
  rewards that strategy. If it now loses to a sibling preset, the
  optimum is between them.
- **Cards:** design new cards that explicitly reward the winning
  plan. If `workers` won in MC, design new cards that scale with
  Worker count (Iron Golem's redesign already did this — its
  capability score went from 0 to 0.44). Cards that win the meta
  are the format-defining cards you're after.

The tournament is also the natural place to drop in a *new* spice
candidate: include it in a deck that pairs with the winning variant,
see if its inclusion shifts win-rates by ≥5%. If it does, the card
is contributing real strategic weight.
