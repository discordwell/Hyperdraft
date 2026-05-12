---
name: spice-pass
description: "Use when designing, implementing, validating, or iterating Hyperdraft custom-set spice passes: format-defining cards, synergy packages, capability tests, variant tournaments, balance tournaments, and engine or AI fixes found during the pass."
metadata:
  short-description: Design and validate spice passes
---

# Spice Pass

## Purpose

A spice pass turns a functional but flat card set into a set with format-defining cards, build-arounds, synergy packages, and measurable archetypes.

Use this skill when the user asks to make a custom set more interesting, add pushed cards, design build-around mythics, validate whether spice cards matter, run capability tests, or tune the AI/harness around a new engine's meta.

For detailed historical notes, thresholds, porting lessons, and command examples, read `references/spice-methodology.md`.

## Design Gate

Every spice card should intentionally hit 1-3 broken-card patterns:

1. Disproportionate efficiency
2. Hard to interact with
3. Snowball value engine
4. Compression / threat-and-answer
5. Asymmetric prison
6. Free or alternative cost
7. Tutoring and consistency
8. Recursion / persistence
9. Tempo theft
10. Two-card combo enablement
11. Build-around / synergy-dependent payoff

Pattern 11 needs special validation. Generic tournament deckbuilders often omit the support cards, so a good build-around can look bad in a generic tournament.

## Workflow

1. Pick one pilot set. Do not roll a spice methodology across many sets before validating one pass.
2. Survey the set file once. Note existing factions, legends, subtypes, resource constraints, and already-wired helpers.
3. Design 8-15 spice candidates across rarities and archetypes. Prefer cards that make a deckbuilder say "build around this" or "this plus that changes the format."
4. Map each design to engine support. Sort into phases:
   - Phase A: current engine and helpers only.
   - Phase B-1: small, broadly useful engine extensions.
   - Phase B-2: complex but possible with current architecture.
   - Phase B-3: defer until missing engine capability exists.
5. Implement Phase A first with focused tests. If you uncover bugs, gaps, or stale harness assumptions, fix those before moving to the next phase.
6. Add/update the set's synergy registry for build-around cards.
7. Run per-card capability tests before trusting tournament results.
8. Run a tournament for set-level balance after capability tests pass.
9. Iterate on cost, stats, support cards, AI heuristics, or engine hooks based on measured failure mode.

## Capability Test

MTG spice cards use:

```bash
python scripts/play/capability_test.py --set <CODE> --card "<NAME>" --games 10
python scripts/play/capability_test.py --set <CODE> --all --games 10
```

Minecraft TCG uses:

```bash
python scripts/play/minecraft_capability_test.py --card "<NAME>" --games 10
python scripts/play/minecraft_capability_test.py --all --games 10
```

The MTG harness currently imports registered synergy maps from `scripts/play/capability_test.py`; if a new set has a synergy module, add it to `_load_synergy_registry`.

Primary metric:

```text
capability_score = focal_cast_per_game * win_correlation
```

Use `0.30` as the default MTG threshold. Slower-economy engines may need lower thresholds or longer game horizons.

## Synergy Packages

For each build-around focal, declare 8-12 partner card names from the same set. Partners must include both effect support and cost/resource support. The capability deck should be able to cast the focal and make it matter.

MTG convention:

```text
src/cards/custom/<set>_synergies.py
<SET>_SYNERGY_PACKAGES: dict[str, list[str]]
```

Minecraft convention:

```text
src/cards/minecraft/synergies.py
MC_SYNERGY_PACKAGES: dict[str, list[str]]
```

Run or update registry sanity tests so typos fail early.

## Tournament Validation

After individual capability tests, use set-level tournaments to validate the format shift:

```bash
python scripts/play/custom_set_tournament.py \
  --games 3 --max-turns 14 --difficulty hard \
  --sets "GHB,NRT,SPMC,MHA,LTR,PKH,ZLD,OPC,JJK,FINC,DMS,SWR" \
  --out logs/tournament_spice.json \
  --report logs/tournament_spice_report.txt \
  --seed 42 --workers 4
```

Read high win rates as a diagnosis, not just success. A 55-65% band is usually a strong but plausible target. A 70%+ set often means one card or package is too dominant. High error counts often mean timeout pressure from long-value games; rerun with higher `--max-turns` before redesigning.

## New Engine Port

Before capability tests on a new or weakly understood engine, confirm that the AI plays the format's real meta. If the meta is unknown, run a variant tournament first:

```bash
python scripts/play/variant_tournament.py --engine minecraft \
  --variants balanced,aggro,ramp,explore,workers,random,largest \
  --decks builder,miner,raider --games 6 \
  --out logs/mc_variants.json
```

Parameterize every important AI axis, not just card choice: resource acquisition, attack target, defense/blocking, tutoring/searches, and sacrifice priorities. Include `random` and ideally a fully-random floor so strategy quality has a real baseline.

## Codex-Specific Notes

Do not spawn parallel agents just because the Claude source did. In Codex, spawn subagents only when the user explicitly asks for delegation or parallel agent work. If they do, split design survey, implementation, review, and tournament verification into bounded, non-overlapping tasks.

When implementing cards from this skill, also follow `$implement-mtg-cards`.

## Phase Commit Shape

A phase commit or PR summary should answer:

- Which cards landed and what role each plays.
- Which engine extensions landed and why they are broadly useful.
- Which designs were simplified or deferred.
- What tests were added.
- What capability/tournament results say.
- What residual risks remain.
