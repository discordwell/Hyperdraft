# Per-deck strategy plans

This directory holds per-deck strategy plans. Each file is named
`<deck_name>_plan.md` and is paired with `docs/strategy/minecraft.md`
(format-level wisdom):

- `docs/strategy/minecraft.md` — general MC TCG strategy. What's true
  regardless of which deck you're piloting (mining priorities, combat
  rules, day/night math, common AI weaknesses).
- `docs/decks/<deck>_plan.md` — strategy specific to one deck. What
  *this deck* wants to do (win condition, target turn, key cards,
  mulligan policy, anticipated weaknesses).

The pilot subagent in `/ultra-loop --game minecraft` reads BOTH before each game.
Both are persistent across sessions — fresh Claude instances bootstrap
their understanding from these files.

## Plan template

Use this shape when writing a new deck plan:

```markdown
# <Deck Name> — Plan

## Composition summary
- N cards total. Brief inventory of card-type counts (Workers,
  Hostiles, Structures, Tools, Actions). Highlight unusual ratios
  (e.g. "24% Workers — twice the typical density").

## Win condition
One sentence: how does this deck win games? (e.g. "Hostile flood +
Pillager Patrol Raider lord + Night ATK boost for a turn-7 lethal.")

## Target turns
- T1-2: <opening goal>
- T3-5: <midgame goal>
- T6-N: <closer goal>

State the *expected lethal turn* explicitly. If the deck doesn't have a
clean clock, say so — that's a real construction issue.

## Key cards
- **Card name** — what it does for this deck specifically (the
  format-level effect is in the strategy doc; here, explain its role
  in *this* plan).

## Mulligan policy
- Auto-mull: <hands that don't function>
- Auto-keep: <ideal hands>
- Salvage: <marginal hands and how to play them>

## Play priorities (order)
1. <highest-priority decision>
2. ...
N. <lowest>

## Anticipated weaknesses
- What kinds of opponents/decks/strategies counter this plan? What's
  the failure mode when the wrong opening is dealt?

## Iteration log
Append after each game piloted with this deck. Include date, opponent,
outcome, and one sentence of what was learned.

- 2026-MM-DD: <opp> — <W|L|D> in T turns. <one-line lesson>
```

## When to update a plan

- After every game where the pilot uses the deck. The coach updates the
  iteration log + refines sections that the game contradicted.
- When the deck composition itself is changed in `logs/mc_decks_*.json`
  or the starter registry, the plan must be revisited (composition
  summary will lie otherwise).

## When to retire a plan

- When the deck is removed from the registry.
- When the plan fails to reflect the deck's actual play pattern after
  3+ iterations — the deck or the plan is fundamentally wrong; rewrite
  from scratch rather than patching.
