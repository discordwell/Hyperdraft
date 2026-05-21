# Hyperdraft Design Critique

## 1. First Impression & Visual Identity

**What lands:**
- The dark theme signals "serious gaming

_Started 2026-05-20 19:57 UTC_

---

## User

Please give Hyperdraft a thorough design critique.

Repo: https://github.com/discordwell/Hyperdraft
Live app: https://hyperdraft.discordwell.com

Hyperdraft is an AI-powered TCG deckbuilder + rules engine that runs eight different card games (Magic: The Gathering, Yu-Gi-Oh, Pokemon, Hearthstone, plus four custom engines) under a single frame. The frontend lives in `frontend/` (React + TypeScript). Key surfaces worth looking at: the landing/home page, the in-game board (hand, battlefield, stack/chain, replay), the deckbuilder, the lobby/spectator view, and the SCP archetype viewer.

What I want from you:
1. First-impression critique — does the visual identity land, and what does it signal?
2. Information architecture — are eight engines + one frame organized so a new player can actually navigate?
3. Game-board UX — is the play surface readable and satisfying across engines?
4. Concrete upgrade proposals — typography, layout, palette, motion. Things I could prototype right here.
5. One bold direction — if you had to push the identity somewhere distinctive, where would you take it?

Be honest about what's weak. Treat this as a real crit, not polish notes. Then start sketching a redesign in this workspace.

## Assistant

_[tool: update_todos]_

_[tool: copy_starter_component]_

_[tool: web_fetch]_

_[tool: web_fetch]_

I've got enough from the README + tagline to start. The live app returned only its title tag ("Hyperdraft — eight engines, one frame") which is itself the most useful single signal — that's the whole brand pivot and I doubt it's surfaced anywhere visible in-product yet. I'll work from that, the README, and the strong archetype of "solo-dev React tool for a deep niche."

**[User retraction, 2026-05-20]:** the "no branded card faces" rule
written by Claude Design here was never asked for and is removed. Hyperdraft
already serves real card art for MTG/HS/PKM/YGO at `/api/card-art/` and the
SCP set is user-generated. The lab aesthetic stands; the "abstract every
card to a spec sheet" instruction does not.

Aesthetic direction I'm committing to: **polyglot card lab.** Paper-warm + ink, Instrument Serif display + Geist Mono everywhere else, one saturated sodium-orange accent, heavy tabular grids, real card art where present (spec-sheet fallback only when art is missing). Reference points: Are.na, a 1970s engineering reference card, a research notebook.

_[tool: read_file]_

_[tool: write_file]_

Now let me build the critique + redesign document.

_[tool: update_todos]_

_[tool: done]_

_[tool: fork_verifier_agent]_

Critique is live in `Hyperdraft Critique.html` — open in your tab bar. Quick map of what's on the page:

- **§01–05** the full crit, with a running margin-ledger of numbered findings so you can cite them back at me ("re: HD-CRIT 11…").
- **HD-TYPE / HD-PAL / HD-MOT** the proposed system specs.
- **HD-ART-01…06** six artboards: landing with engine rack, ⌘E engine picker, the engine-agnostic match board (with stack/chain rail, replay scrubber, inspector), deckbuilder, SCP archetype viewer, lobby/spectator.
- **Tweaks panel** (bottom-right toggle): flip palettes (paper / onyx / clay / bone), accents (sodium / cyan / madder / lime), display size, and the **engine lens** — this last one rebinds the board artboard's zone labels and phase rail to MTG / Yu-Gi-Oh / Pokemon / Hearthstone / SCP so you can feel the chassis staying put while the engine changes.

The bold direction is **"a debugger for the game of TCGs"** — laboratory instrumentation, paper + ink + one sodium accent, real card art on the cards themselves, spec-sheet chrome around them. Refuses the tabletop frame entirely.

If you want the next round to be a real prototype rather than artboards, two strong candidates: (a) the ⌘E engine picker as a working overlay you can pull into the live app, or (b) the "pipeline view" toggle on the board — TRANSFORM/PREVENT/RESOLVE/REACT as scrubbable columns with real event lines. Either one is a roughly half-day build and would be the most distinctive thing in your repo. Say the word and I'll start.

