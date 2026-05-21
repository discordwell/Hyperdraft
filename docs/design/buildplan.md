# HYPERDRAFT — buildplan from the 2026-05-20 brand notes

## Context — what you told me, condensed

1. **"Eight engines, one frame" is out.** Many more engines coming; tagline boxed it in. ✓ done in `d80f872e`.
2. **HYPERDRAFT is always full caps** in user-visible copy. ✓ done.
3. **New pitch — game-cabinet sleepover.** Rummaging through the cabinet at a sleepover, finding TCGs nobody's played, no metas, figure it out as you go. First-time-play on demand.
4. **The audience.** People who were told they were smart as children and it stuck. Adults who treat unfamiliar rules as a puzzle, not friction. They don't want a tutorial; they want a calm room and an interesting box.
5. **The lab archetype stays.** Calm-room visual supports the cabinet metaphor.
6. **The "see the rules running" / "debugger for TCGs" pitch is retired.** Every TCG has a stack; nobody calls MTG's stack revolutionary. The pipeline is good engineering, not the headline.

This buildplan turns those into shippable slices. It assumes the lab pivot, EnginePicker, Timeline, and BIG MOVES 17/19/20 are already on `main`; that the ⌥P PipelineView (BIG MOVE 18) stays power-user behind a chord; and that Pipeline-the-Game has been ripped out (`65b67aa7`) and is not coming back.

The cabinet pitch only works if first-time play is fast, rules are at hand, and the engine list scales past 20+ entries. Everything below serves one of those three.

---

## Phase A — Cabinet onboarding (~3–5 days)

The core pitch. First-time play on demand, no friction, smart-kid-adult voice.

### A1. Discovery default — "the one you haven't played"

LocalStorage flag `hd.played_engines: GameModeId[]`, written when a user starts (or finishes) a match. EngineRack annotates each row: untouched engines get a sodium "NEW" pill. Hero eyebrow rotates: if anything has been played, it becomes `"You haven't tried <engine>. Pull it off the shelf."`

| File | Change |
|---|---|
| `frontend/src/stores/discoveryStore.ts` *(new)* | Zustand store: `playedEngines`, `markPlayed(id)`, `pickUnplayed()`. Persisted to localStorage. |
| `frontend/src/components/lab/EngineRack.tsx` | New "NEW" sodium pill on rows whose `id` isn't in `playedEngines`. |
| `frontend/src/pages/Home.tsx` | Eyebrow chip + maybe a secondary CTA reads from `pickUnplayed()`. |
| `frontend/src/pages/GameView.tsx` + the 8 per-engine views | Call `markPlayed(mode)` on first frame. |

**Outcome:** every visit feels like a different game on the shelf is glowing. First-time user sees the rack as-is.

### A2. Rules-at-a-glance — `<RulesSheet>`

Per-engine one-page rules reference. Lab-styled plate, slides in from the right via `?`. Sections: zones, turn structure, win condition, one quirk to know. Voice guardrail: written for a smart-kid-adult — if it explains what "tapping" means, you've gone too far.

| File | Change |
|---|---|
| `frontend/src/data/rulesSheets/{mtg,hearthstone,pokemon,yugioh,minecraft,finance,depths,scp,cats}.md` *(new)* | ~150 words per engine. Markdown. |
| `frontend/src/components/lab/RulesSheet.tsx` *(new)* | Slide-over panel, markdown renderer (react-markdown or a tiny inline pass), Esc to close. |
| `frontend/src/hooks/useQuestionMark.ts` *(new)* | Global `?` keybind. Same pattern as `useCmdE`. Ignores typing targets. |
| `frontend/src/App.tsx` | Mount `<RulesSheet />` globally; reads current engine from route params. |

**Outcome:** anywhere in the app, hit `?` to learn how this engine works without leaving the page. No tutorial mode, no popup wall.

### A3. First-match flow tightening

Home → "Open a match" → in-match in ≤3 clicks for engines with default decks. The current 3-column matchbuilder is busy — HD-CRIT-002 retraction #6 already flagged this. Replace with progressive disclosure: a single primary CTA that uses the rack-highlighted engine and the user's last-used deck; "Customize" reveals the form.

| File | Change |
|---|---|
| `frontend/src/pages/Home.tsx` | Match-builder plate compresses to one row by default. "Customize" toggle reveals difficulty/deck/ultra-agent fields. Last-used selections persisted via discoveryStore. |

**Outcome:** skim → click → play.

---

## Phase B — IA that scales past 20 engines (~2 days)

Today's rack is 9 rows. At 25+, vertical scroll alone won't cut it.

### B1. Rack filters + sort

| File | Change |
|---|---|
| `frontend/src/components/lab/EngineRack.tsx` | Controls bar above the rack: mono search input, sort selector (alphabetical · by completeness · untouched first). |

### B2. Picker filters

| File | Change |
|---|---|
| `frontend/src/components/lab/EnginePicker.tsx` | Same controls as B1 inside the ⌘E overlay. Typing while open filters in real time. |

### B3. New-engine ergonomics

The `.claude/commands/new-game.md` slash command builds new engines today but doesn't register them in the lab rack — that's a manual edit to `engineMeta.ts`. Fix that.

| File | Change |
|---|---|
| `.claude/commands/new-game.md` | Final stage writes to `frontend/src/components/lab/engineMeta.ts` so a new engine appears in the rack + picker automatically with sensible default stats. |

---

## Phase C — Per-engine GameView ports (HD-CRIT-001 #04, ~5–7 days)

The per-engine GameViews (HS, PKM, YGO, MNR, FIN, DPT, SCP, Cats) still ship inline `bg-slate-900` / `border-amber-600` / `ygo-gold` classes. Two costs:
1. They look mid against the lab-pivoted Home / ReplayView / RulesDiff.
2. They visually argue "this is *the* Hearthstone client" / "this is *the* Yu-Gi-Oh client" — exactly what HD-CRIT-001 #04 said to retreat from.

### C1. Template port: HSGameView → lab

Pick one engine (HS) and port it cleanly. Output a portable pattern the rest can follow.

| File | Change |
|---|---|
| `frontend/src/pages/HSGameView.tsx` | Replace inline dark-foil utility classes with lab token classes. Keep the board *layout* (zones, lanes); only the chrome changes. Document the pattern in a comment header. |

### C2. Parallel port of the other 7 views

Spawn one Opus agent per file with C1 as the template. ~½ day per view, parallelized.

| File | Change |
|---|---|
| `frontend/src/pages/PKMGameView.tsx` | Lab port. |
| `frontend/src/pages/YGOGameView.tsx` | Lab port. |
| `frontend/src/pages/MCGameView.tsx` | Lab port. |
| `frontend/src/pages/FinanceGameView.tsx` | Lab port. |
| `frontend/src/pages/DepthsGameView.tsx` | Lab port. |
| `frontend/src/pages/SCPGameView.tsx` | Lab port. |
| `frontend/src/pages/CatsGameView.tsx` | Lab port. |

Each agent brief gets explicit "do not mimic source-game chrome" — that's the HD-CRIT-001 #04 restraint.

### C3. Unified board template *(only if duplication makes itself obvious)*

After C2, if a clean factoring emerges, extract the common layout into `frontend/src/components/lab/BoardChassis.tsx`. **Skip if not** — premature abstraction is worse than duplication.

---

## Phase D — Inspector demotions (~½ day)

The PipelineView overlay (BIG MOVE 18) and `/rules-diff` are good engineering. They are not the pitch. Push them out of the discovery path; keep them reachable for power users.

### D1. Confirm ⌥P stays optional

Verify the PipelineView overlay renders only when ⌥P is pressed — not as a panel on the GameView header, not on first paint. Probably already true; spot-check.

| File | Change |
|---|---|
| `frontend/src/pages/GameView.tsx` | Audit: PipelineView is gated behind `pipelineOpen` toggle, not in the persistent header. |

### D2. Demote `/rules-diff` from Home library

Currently `/rules-diff` is one of the 6 Home library tiles. That puts engine-comparison in front of a first-time user who hasn't played anything. Move it to a "Deep dive" footer block alongside `/replays` and `/admin/training`.

| File | Change |
|---|---|
| `frontend/src/pages/Home.tsx` | Remove "Rules diff" library tile; add a small "Deep dive →" footer link near the existing footer rail. |

---

## Phase E — Phase rail visibility (v1 #12, ~1 day, folds into Phase C)

HD-CRIT-001 #12 called out that the phase rail must always be glanceable, especially through combat. This is small and naturally rolls into the per-engine ports in Phase C — port each GameView's phase indicator to the lab `.lab-phases` utility at the same time as the chrome.

---

## Sequencing

**Suggested order: A2 → A1 → A3 → C1 → C2 (parallel) → D2 → B1 → B2 → B3 → D1 → C3.**

Why this order:
- **A2 first** because the rules-sheet pattern is what makes "no tutorial" *honest*. Without it, "figure it out" reads as "we didn't bother explaining."
- **A1 next** because it gives the home page a reason to feel different for returning users — discovery is the loop.
- **A3** because the cabinet pitch dies if the path to a match is still a 12-field form.
- **C1 + C2** because the per-engine ports are the bulk of the visible-coherence work and benefit from parallelization once C1 sets the template.
- **D2** is a small move with high signal — gets `/rules-diff` out of the discovery path.
- **B** (IA scale) is polish until the engine count actually pushes past ~15.
- **C3** only if it earns itself.

## Out of scope

- **Pipeline-the-Game / `/pipeline`** — ripped out at `65b67aa7`. Do not re-spawn under any framing.
- **"Inspector / debugger for TCGs" as the pitch** — retired. The overlay stays; the framing doesn't.
- **New games / new engines** — this plan makes the cabinet *readable*, not bigger.
- **Spectator chrome inside `/m/HD-XXXX`** — still legacy dark; defer.
- **Deckbuilder lab port** — significant work; defer.

## Open questions

1. Are the rules-sheet markdown files something you want to write yourself (voice-critical) or want me to draft a first pass per engine?
2. For A1's localStorage discovery state — single browser-local store fine, or do you want it associated with a user account when one exists?
3. For Phase C, are you OK with the parallel-agent dispatch pattern again? (Lab pivot is on `origin/main` now, so the previous worktree-stale-main issue won't recur.)
