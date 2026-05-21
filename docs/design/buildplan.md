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

## Phase C — Lab/game seam clarity (~1–2 days)

**The previous draft of this phase was wrong.** It proposed porting all 8 per-engine GameViews to lab tokens. That would homogenize away each game's identity, which is load-bearing — HS *should* feel like HS, YGO *should* feel like YGO. See `docs/design/brand.md` for the mad-scientist / lab-as-meta-frame framing and the explicit retraction of HD-CRIT-001 #04.

The actual work is at the **seam** between lab and game. The lab posture lives on the surfaces that are *between* games; each match's interior keeps its own chrome.

### C1. GameViewLayout header → lab posture

`frontend/src/components/brand/GameViewLayout.tsx` wraps every GameView with a header strip (HYPERDRAFT mark, mode badge, breadcrumb, opponent/player names). That strip is the constant seam — it carries the player from the lab into the experiment and back. Port the strip itself to lab posture (paper/ink/sodium, Geist Mono telemetry, hairline rule below) while leaving the body — the actual game board — untouched.

| File | Change |
|---|---|
| `frontend/src/components/brand/GameViewLayout.tsx` | Replace foil-era header chrome with lab tokens. Keep all existing props (mode, matchId, turn, phase, names). Add a small "← Lab" button on the left that returns to Home. |
| `frontend/src/components/brand/Header.tsx` | Same treatment if it surfaces above unified pages — confirm it doesn't double up with `GameViewLayout`. |

### C2. Replays index → lab

`frontend/src/pages/Replays.tsx` is a between-games index — list of past matches across all engines. Currently brand-tile dark grid. Port to a lab rack analogous to `EngineRack`: each row is a match (engine code, turn count, winner, timestamp), mono telemetry, hairline rules.

| File | Change |
|---|---|
| `frontend/src/pages/Replays.tsx` | Lab port. Same grid information density, lab posture. |

### C3. WatchLive → lab

`frontend/src/pages/WatchLive.tsx` is the live-matches lobby — between games. Lab posture.

| File | Change |
|---|---|
| `frontend/src/pages/WatchLive.tsx` | Lab port. Live-pulse acid dots, mono match IDs, hairline-ruled table mirroring HD-ART-06's lobby artboard. |

### C4. SpectatorView outer chrome → lab

`frontend/src/pages/SpectatorView.tsx` wraps a live in-progress match for spectators. Like `GameViewLayout`, it has an outer header + the game body. Port the *outer* header to lab posture; leave the embedded game chrome alone — when you're watching a Hearthstone match, the board still looks like Hearthstone.

| File | Change |
|---|---|
| `frontend/src/pages/SpectatorView.tsx` | Port the wrapper (top header, watch-publicly indicator, copy-link button) to lab tokens. Body — which renders the live game state — untouched. |

### Explicitly NOT in Phase C

- The 8 per-engine GameView files (`HSGameView`, `PKMGameView`, `YGOGameView`, `MCGameView`, `FinanceGameView`, `DepthsGameView`, `SCPGameView`, `CatsGameView`) **stay as they are**. Each game's identity is intentional.
- No parallel agent dispatch on the GameViews. (Was a bad idea on a wrong premise.)
- No "unified board chassis" abstraction. The boards *should* be different.

---

## Phase D — Inspector discoverability (~½ day)

The PipelineView overlay (BIG MOVE 18) and `/rules-diff` are good engineering and the audience cares about the stack. Keep them reachable; just don't make them the headline. **Not hidden, not demoted, toggle-gated.**

### D1. ⌥P stays a chord with a quiet hint

Verify the PipelineView overlay renders only when ⌥P is pressed — not as a panel on the GameView header, not on first paint. Add a small mono "⌥P · pipeline" hint to the GameViewLayout header strip (Phase C1) so a curious user discovers the toggle exists without it being thrown in their face.

| File | Change |
|---|---|
| `frontend/src/pages/GameView.tsx` | Confirm `pipelineOpen` is the only entry. |
| `frontend/src/components/brand/GameViewLayout.tsx` | Add a `⌥P · pipeline` mono hint, ink-3 color, in the header strip. Disappears when the overlay is open. |

### D2. `/rules-diff` stays in the Home library row

No demotion. The library row already lives below the main flow (configure → advanced → library), so a first-timer sees it last — that's the right amount of prominence. Smart users browsing the tiles find it.

| File | Change |
|---|---|
| `frontend/src/pages/Home.tsx` | No change. (Previously this said "demote"; that was wrong.) |

---

## Phase E — Phase rail visibility (v1 #12, scope reduced, ~½ day)

HD-CRIT-001 #12 called out that the phase rail must always be glanceable, especially through combat. This is still real, but it lives **inside** each game's chrome, so each engine handles it in its own idiom — there's no cross-engine "use the lab `.lab-phases` utility" treatment now. Each GameView gets a one-line audit: is the current phase legible at a glance? If not, surface it more clearly *in that game's visual vocabulary*. ~½ day across all 8.

| File | Change |
|---|---|
| each `<Engine>GameView.tsx` | Audit phase-rail visibility; bump contrast or move the indicator if it's getting eaten by the rest of the chrome. Game-native styling. |

---

## Sequencing

**Suggested order: A2 → A1 → C1 (with D1's ⌥P hint folded in) → A3 → C2 → C3 → C4 → B1 → B2 → B3 → E.**

Why this order:
- **A2 first** because the rules-sheet pattern is what makes "no tutorial" *honest*. Without it, "figure it out" reads as "we didn't bother explaining."
- **A1 next** because it gives the home page a reason to feel different for returning users — discovery is the loop.
- **C1 + D1 together** because the GameViewLayout header strip is where the ⌥P hint lives; do them in the same pass.
- **A3** because the cabinet pitch dies if the path to a match is still a 12-field form.
- **C2 / C3 / C4** are the remaining between-games surfaces; mechanical lab ports.
- **B** (IA scale) is polish until the engine count actually pushes past ~15.
- **E** is per-engine phase-rail polish, no cross-engine homogenization.
- **D2** has no work (rules-diff stays where it is).

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
