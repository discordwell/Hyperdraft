# Spice Methodology Reference

## When a Set Needs Spice

A set is flat when most creatures are stat lines or simple ETB cards and no card defines an archetype. A spice pass should introduce cards that are deliberately strong, interesting, and measurable.

Good target outcomes:

- A deckbuilder can identify build-arounds.
- Multiple archetypes get real payoffs.
- The AI can cast and use the new cards.
- Capability tests show the focal cards matter in supported decks.
- Tournament results move in a plausible band rather than only adding noise.

## Broken-Card Pattern Details

Use 1-3 of these per card:

- Disproportionate efficiency: impact far above rate for the mana/resource cost.
- Hard to interact with: ward, protection, hexproof-like effects, indestructible, recursion.
- Snowball value engine: each turn compounds the previous turn.
- Compression / threat-and-answer: one card is both proactive and reactive.
- Asymmetric prison: opponents are constrained more than the controller.
- Free or alternative cost: pitch cost, graveyard cast, exile cast, cascade-like access.
- Tutoring and consistency: finds the exact piece.
- Recursion / persistence: graveyard or exile becomes a second hand.
- Tempo theft: extra turns, extra combats, time-walk effects.
- Two-card combo enablement: explicit oppressive or infinite pairing.
- Build-around / synergy-dependent: weak generically, excellent with a support package.

## Capability Test Interpretation

`scripts/play/capability_test.py` builds a 60-card synergy deck:

- 4 copies of focal.
- 2 copies of each registered partner by default.
- Same-set filler.
- Basic-land mana base.
- Generic baseline deck as the opponent.

Default MTG command:

```bash
python scripts/play/capability_test.py --set PKH --card "Charizard, Mega Evolved" --games 10
```

The harness reports:

- `focal_cast_per_game`: natural unit for "does the focal land?"
- `focal_win_rate_in_play`: useful for permanents.
- `synergy_deck_winrate`: useful for one-shot spells and overall support shell.
- `capability_score = focal_cast_per_game * win_correlation`.

For permanents, win-correlation is normally win rate while the focal is in play. For one-shot instants/sorceries, use synergy-deck win rate because the spell goes to graveyard after resolving.

Focal-in-opener stacking is intentional. It removes draw variance so the test asks whether the supported card carries when drawn, not whether a small sample found one copy.

## Synergy Registry Design

Partners should be cards that make the focal substantially better and help the deck cast it. Do not choose only thematic cards. Include ramp, fixing, cheap enablers, tribal density, graveyard fuel, or other cost-supporting cards as needed.

Registry requirements:

- Focal name exactly matches the card registry.
- Partner names exactly match existing cards.
- Partners come from the same set unless the harness explicitly supports cross-set tests.
- Add tests or run existing harness checks for missing partners.

If the capability harness does not know a set yet, add the set's module and package attribute to `_load_synergy_registry` in `scripts/play/capability_test.py`.

## Phase Organization

Phase A: current engine only. Good fits include static keywords, lord effects, simple ETB/death/attack triggers, straightforward activated abilities, simple equipment/aura statics, and spell resolves that already match target infrastructure.

Phase B-1: small engine extensions, preferably 30 lines or less and broadly useful. Examples from project history include a new library-search filter, a destruction tracker, cost-reduction conditions, and activated ability preconditions. Ship each with tests.

Phase B-2: complex but possible. Examples include sagas, multi-stage triggers, stack-aware costs, and heuristic-driven modal behavior.

Phase B-3: deferred until engine gaps close. Examples include prompt-driven modal multi-choice outside current helper support, full DFC/transform with separate back faces, persistent copy-creature fidelity, and alternative-cost tracking when the engine does not expose which cost was paid.

## Implementation Checklist

Before committing a spice card:

- Card name and Python constant do not collide with existing cards.
- Self-keywords are wired, not just written in text.
- ETB filters that care about tokens handle `CREATE_TOKEN` as needed and exclude `event.source == src.id` to avoid self-loops.
- Sacrifice listeners watch rewritten `ZONE_CHANGE` events with `reason == "sacrifice"`.
- Activated costs are comma-separated.
- `EXILE_TOP_PLAY` uses `caster`.
- `ATTACH` uses `object_id` and `target_id`.
- Card appears in registry dict and aggregate card list.
- Smoke import passes: `python -c "from src.cards.custom.<set> import NEW_CARD"`.
- Tests include a positive path and at least one edge case.
- Capability test passes or the failure mode is understood and documented.

## Testing Patterns

Use focused card tests for behavior:

- Load test: expected type/subtype/cost/interceptors.
- Positive path: event emits and state changes as intended.
- Edge case: controller filters, wrong subtype, no target, empty library, duplicate trigger, or legality precondition.

Use capability tests for build-arounds:

```bash
python scripts/play/capability_test.py --set <CODE> --card "<NAME>" --games 10
```

Use set tournaments for balance:

```bash
python scripts/play/custom_set_tournament.py --sets "<CODES>" --games 3 --max-turns 14 --difficulty hard
```

If a tournament result is below expectation, inspect whether the card entered decks, was drawn, was cast, and was evaluated correctly by the AI. A tournament can be measuring deckbuilder or AI weakness instead of card weakness.

## AI and Meta Audit

Before trusting capability tests, inspect the AI decisions that matter for the engine:

- Card scoring: does the AI value ramp, engines, and support cards?
- Resource acquisition: does it choose the resources needed to cast the package?
- Attacks: does it target the right player, permanent, structure, or board slot?
- Defense: does it block/trade in a way that matches the format?
- Search/tutor choices: does it find support or only raw stats?

Watch at least one representative game when a score is surprising.

If the meta is unknown, run a variant tournament before capability tests. `scripts/play/variant_tournament.py` supports MTG and Minecraft and is intended to discover which AI bias wins by self-play.

Variant-tournament guidance:

- Include named strategic variants, not only random knobs.
- Include `random`, `largest`, or fully-random baselines.
- Parameterize all important AI axes; a card-choice-only sweep can hide strong shared heuristics on mining, blocking, attacking, or tutoring.
- Tune the default AI toward the winning complete strategy, then rerun capability tests.

## New Engine Port Lessons

The spice methodology ports, but thresholds and hooks do not always port unchanged.

For slower economies, cast rate can cap below MTG norms. Lower the pass threshold or increase `max_turns` only after confirming that the AI is playing the format sensibly.

Expect one small engine extension per new engine pass. Build-around cards often need a hook surface existing vanilla cards did not need.

Separate "card cannot carry" from "AI refuses to use support." The latter should be fixed in AI or harness logic before redesigning the focal.

## Failure Modes and Fixes

Focal never casts:

- Lower cost.
- Add cost-support partners.
- Fix deckbuilder color/resource filtering.
- Teach AI to prioritize ramp/fixing.

Focal casts but does not win:

- Increase payoff.
- Make the payoff scale with the support package.
- Add protection or recursion.
- Ensure the AI uses the triggered/activated mode correctly.

Focal is too dominant:

- Raise cost.
- Reduce stats.
- Remove one compressed mode.
- Add timing limits or once-per-turn gates.

Harness crashes:

- Fix the harness or engine contract first.
- Add a regression test for the failure before continuing the pass.

Tournament result is noisy:

- Increase games.
- Check whether the card entered decks.
- Inspect cast/drawn/card-score metrics.
- Run per-card capability tests instead of relying on aggregate win rate.

## Commit or PR Summary Template

```text
feat(spice): <set> Phase <X> - <summary>

Cards:
- <card>: <role>

Engine extensions:
- <name>: <broad purpose>

Approximations/deferred:
- <item>: <why>

Tests:
- <new tests or commands>

Validation:
- Capability: <scores>
- Tournament: <summary>

Risks:
- <remaining concern>
```
