# Legend of Zelda — slice-8 retrofit audit (Phase 0)

Set: `src/cards/custom/legend_of_zelda.py` (~7724 lines, MTG engine).
Retrofit under repair: slice-8 (8A/8B/8C/8D), all dated 2026-05-19,
commits 64a11535 / 7c6862a9 / f03164c5 / c7230cfa.

## What the retrofit did

116 auto-generated `*_setup` / `*_resolve` helpers across 4 slices that
emit generic SCRY / SURVEIL / MILL / DISCARD / REVEAL_HAND + cross-controller
LIFE_CHANGE / DAMAGE "info-pulse" events, wired to ~110 vanilla cards to clear
a median-depth gate. Two failure shapes:

### (a) Dead-original-clause traps — APPENDED text, only NEW clause wired

The slice-8D commit (c7230cfa) **kept** each card's original rules clause and
**appended** a new "When ~ enters, scry N; each opp …" clause, but the new
`*_setup` registers ONLY the ETB info-pulse — the ORIGINAL mechanic is silently
dead. Confirmed via `git show c7230cfa` (diff shows `-text="…+1/+1."` →
`+text="…+1/+1. When … enters, scry 1; …"`).

**Equipment with dead P/T + keyword + subtype statics (12):**

| Card | Dead static clause | equip |
|------|--------------------|-------|
| Hero's Bow | granted activated ability "{T}: deal 2 to flyer" | {1} |
| Biggoron's Sword | +5/+0, trample, can't block | {3} |
| Mirror Shield | +1/+2 (+ damage-reflect trigger) | {2} |
| Ancient Bow | +1/+1, granted "{T}: deal 3 any target" | {2} |
| Kokiri Sword | +1/+1 | {1} |
| Majora's Mask | +3/+3, menace (+ upkeep -1 life) | {2} |
| Fierce Deity Mask | +4/+4, double strike | {3} |
| Deku Mask | grants Plant + "{T}: Add {G}" | {1} |
| Goron Mask | +2/+2, trample, grants Goron | {2} |
| Zora Mask | +1/+2, can't be blocked, grants Zora | {2} |
| Bunny Hood | +1/+0, haste | {1} |
| Stone Mask | hexproof, can't attack/block | {1} |

Reference pattern (already-correct equipment in same file): Master Sword,
Sheikah Eye of Truth, Hylian Shield, Skyward Sword — all use
`make_equipment_setup(power_mod=…, toughness_mod=…, keywords=[…], equip_cost=…,
granted_triggered_abilities=…)`.

**Artifacts with dead activated abilities (7):** Sheikah Slate, Bomb Bag,
Fairy Bottle (sac ability), Magic Boomerang, Hookshot, Lens of Truth, Ocarina
of Time — each has an original "{cost},{T}: …" (or "Sacrifice: …") ability that
is unwired; only the appended ETB pulse fires.

### (b) Info-pulse cards — text REWRITTEN to match (faithful, not stubs)

Slice 8A/8B/8C (and the land/Spirit-Tracks entries in 8D) targeted cards that
were **truly vanilla** (no rules text). The retrofit ADDED text AND a matching
helper, so the impl is faithful to the (new) text — these fire real
SCRY+LIFE_CHANGE/DAMAGE events that match their printed text. ~90 creatures +
lands. These are NOT broken (helper emits the events the text claims) but are
the generic-info-pulse flavor the campaign wants curbed. Per task PHASE-2 rule
("vanilla-revert only if truly keyword-only") these keep their working text+impl;
lands' mana abilities are engine-native (not setup-driven) so no dead clause.

`_count_*` helper (`_count_triforce_artifacts`, line 3257) is REAL — keep.

## Repair plan

- Phase 1: bulk-delete the 8D equipment/artifact `*_setup` info-pulse helpers
  that we replace with composed static+ETB setups. (8A/8B/8C creature helpers
  are faithful to rewritten text and stay.)
- Phases 2..N: rewrite the 12 equipment to restore P/T + keyword + subtype +
  granted-ability statics via `make_equipment_setup`, keeping the ETB pulse
  (it is in the text). Wire the 7 artifacts' original activated/sac abilities
  via `make_activated_ability`, keeping the ETB pulse.
- FINAL: `tests/test_legend_of_zelda_interceptors.py` — equip each fixed
  equipment and assert the static bonus applies; fire the ETB and assert the
  pulse. Delete `tests/test_zelda_spice.py`.
