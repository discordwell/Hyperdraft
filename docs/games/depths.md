# Depths — Submarine Fleet Card Game Engine

## Design Rationale

Submarines fight a fundamentally different kind of war than tanks, soldiers, or wizards. The defining tension is **stealth versus detection**: a sub that has not been pinged is functionally untargetable; a sub that has been pinged is a slow, fragile target. The defining resource is **finite ordnance**: torpedoes, mines, and decoys are spent objects, not refilled mana. The defining geometry is **vertical**: surface, periscope, mid-water, deep, and crush depth — each band gates what weapons reach you and what sensors see you. A submarine engine that fails to model these three things will feel like reskinned MTG with anchor icons. Depths is built around them.

To keep the engine implementable on the existing `Event → TRANSFORM → PREVENT → RESOLVE → REACT` pipeline, every submarine-themed mechanic is expressed as a discrete, synchronous game action: `DETECT` is an event that flips a Vessel's `detected` flag, `DIVE` is an event that decrements its depth band, mines are static permanents that emit a damage event when an opponent enters their depth band, oxygen is a per-Vessel counter consumed by activated abilities. Stealth is not "secret information" — it is public state that *gates targeting*, which is something the engine already supports through `TargetingSystem`. The four archetypes (Wolfpack aggro, Silent Hunter stealth-control, Carrier swarm, Deep-Strike combo) emerge naturally from how each interacts with the depth ladder, ordnance economy, and detection pings — not from new keywords nailed onto the side.

---

## 1. Win Condition

**Sink your opponent's flagship — or sink their entire fleet.**

Each player starts with one **Flagship** (HP 25, depth-locked at Periscope, can't dive) on the board. A player loses when *either*:
- Their Flagship's `hull` reaches 0, **or**
- They have no Vessels on the board AND no Vessels in their hand or deck (fleet wipeout — a "scuttle loss").

This dual condition prevents stall: a player whose Flagship is well-defended but whose deck has been milled out still loses if their last Vessel sinks. There is no separate "life total" pool; the Flagship *is* the life total, expressed as a normal Vessel with hull and a fixed depth slot. This makes hull-repair, hull-counter, and "transfer damage to flagship" effects all just damage redirection — already a primitive the engine handles.

> **Why it's submarine-y**: WWII submarine campaigns ended when the carrier or battleship anchoring the fleet went down. The Flagship-as-life-total mirrors that — and the scuttle-loss clause prevents the cheese of "hide the Flagship at 25 HP and run the clock."

---

## 2. Turn Structure

Phases per turn, in order. Each phase emits `PHASE_START` / `PHASE_END` events that triggers can hook.

| Phase | Steps | Allowed actions |
|-------|-------|-----------------|
| **DIVE** (Beginning) | Untap, Resupply, Recon | Untap exhausted Vessels; gain 1 Torpedo Charge; draw 1 |
| **MANEUVER** (Pre-engagement Main) | — | Deploy Vessels, attach Crew/Weapons, change depth band, lay Mines, play Doctrine cards, activate abilities |
| **ENGAGEMENT** (Combat) | Declare Attackers, Detection Resolution, Counter-Detection, Damage | Declare attacks (and which depth band you fire from); detection pings flip targeting eligibility; defender may declare interceptors; damage resolves with depth-band modifiers |
| **REGROUP** (Post-engagement Main) | — | Same as Maneuver (resupply doesn't refire) |
| **SURFACE** (End) | Cleanup, Sonar Decay | Discard down to hand limit (8); all "until end of turn" detection pings expire; oxygen counters tick down on submerged Vessels |

**Why this layout (deviates from MTG)**: The new step is **Detection Resolution** between Declare Attackers and Damage. In MTG, declaring an attack also commits the attacker as a legal damage source. In Depths, an undetected attacker may not actually be targetable by interceptors — so the defender first gets a chance to *try to detect* attackers (spend Sonar Charges, activate sonar abilities) before declaring blockers. This makes stealth a real mechanic instead of a flat "can't be blocked" keyword. Justifies one extra step. The rest of the structure mirrors MTG closely so the existing `TurnManager` can drive it with minimal subclassing.

---

## 3. Resource Model

**Multi-resource: Torpedo Charges (offense) + Sonar Charges (sensors), with a Hearthstone-style ramping ceiling.**

Each player has two stockpiles:
- **Torpedo Charges** (`tc`) — spent to play Vessels, fire Torpedo Actions, and pay attack costs
- **Sonar Charges** (`sc`) — spent to detect opposing Vessels, pay Doctrine costs, and activate Crew abilities

At the start of each turn (Resupply step), a player gains **1 of each** up to a per-turn cap that grows with turn number: cap is `min(turn_number, 10)` for both pools. Unspent charges **persist** across turns up to the cap (so saving for a big turn matters but you can't snowball infinitely). Cards print costs as `{2T, 1S}` ("2 torpedo, 1 sonar"). A handful of Doctrine cards print **hybrid** costs `{X(T/S)}` payable from either pool — these are the "flexible" cards.

Why two pools and not one: it forces archetypes to commit. Wolfpack aggro burns through Torpedo Charges on cheap Vessels; Silent Hunter banks Sonar to weaponize detection; Carrier dumps Torpedo on bench-Vessels; Deep-Strike combo hoards Sonar for late-game finisher activations. With one pool, all archetypes converge to the same curve.

Implementation: this maps cleanly onto the existing `ManaSystem` / Hearthstone mana adapter pattern. We'll subclass `ManaSystem` as `DepthsChargeSystem` with two parallel pools, and the cost parser will accept `T` and `S` symbols alongside the existing `{n}` generic.

> **Why it's submarine-y**: Subs do not run on mana. They run on *finite consumables* — torpedoes that must be reloaded, batteries that drain when running silent, and active sonar pings that give away your position. The two-pool model encodes the eternal sub-warfare tradeoff: do I shoot or do I look?

---

## 4. Zones

Standard zones (existing `ZoneType` enum suffices):
- `LIBRARY` — deck (40 cards)
- `HAND` — visible only to owner; cap 8
- `BATTLEFIELD` — shared, holds all Vessels, Mines, and attached Crew/Weapons
- `GRAVEYARD` — "Wreckage" in flavor text; sunk Vessels and spent Actions
- `EXILE` — "Lost at Sea"; permanent removal
- `STACK` — for ability resolution

**Engine-specific spatial structure: the Depth Ladder.** This is *not* a new `ZoneType` — every Vessel on the battlefield carries a `depth_band` value in `obj.state` (one of `SURFACE`, `PERISCOPE`, `MID`, `DEEP`, `CRUSH`). Mines also carry a depth band. The depth band is **public information** that gates two things:
1. **Targeting**: weapons print "hits SURFACE/PERISCOPE only" (depth charges) or "hits MID/DEEP only" (homing torpedoes); a target at the wrong depth is illegal
2. **Detection cost**: detecting a Vessel at DEEP costs +2 Sonar Charges versus detecting one at SURFACE

Depth is changed by the `DIVE` and `SURFACE_VESSEL` events (one band per activation, costs 1 Sonar Charge to dive, free to surface). This deliberately echoes Minecraft's column system but uses *vertical bands* instead of *lanes* — fewer slots (5 bands vs. 3 columns), no "frontmost" rule, and depth is per-Vessel rather than per-column. Implementation-wise it's a single `state.depth_band` enum field on each Vessel, no new zones, no new grid data structure on `GameState`.

There is **no separate Carrier Hangar zone**: cards that "deploy a Drone Vessel" use the existing `CREATE_TOKEN` event with the new Vessel card type. Bench-style storage is unnecessary because depth bands give vertical separation already.

> **Why it's submarine-y**: A real sub commander's first decision every minute is "what depth?" — too shallow, you eat depth charges; too deep, your own torpedoes can't reach the surface fleet; below crush depth, you implode. The five bands give that decision a discrete game-state expression.

---

## 5. Combat Math

**Engagement model**: simultaneous damage, depth-band modifiers, and a stealth-check window between attack declaration and damage.

Each Vessel has `power` (torpedo damage) and `hull` (HP). Hull damage persists across turns until repaired (no MTG-style cleanup-step heal). A Vessel with `damage >= hull` is sunk and moves to Wreckage.

### Combat steps
1. **Declare Attackers**: active player picks Vessels (must be untapped, not summoning-sick) and declares for each one (a) target Vessel or opposing Flagship, (b) firing depth band — usually their own. Attacker becomes tapped.
2. **Detection Resolution**: defender may spend Sonar Charges to detect undetected attackers. Each attacker has a `detected` flag (default false on entry). Detecting costs `1 + depth_difficulty` Sonar where depth_difficulty is 0 at Surface, 2 at Deep. An *undetected* attacker cannot be targeted by Interceptors but still deals its damage.
3. **Declare Interceptors** (defender's blockers): only **detected** attackers may be intercepted. Each interceptor is one Vessel matched 1:1 with one attacker. Interceptor must be at a depth band reachable from the attacker's target depth (within 1 band).
4. **Damage**: simultaneous. If intercepted, attacker and interceptor deal their power to each other. If unintercepted, attacker deals its power to its declared target. **Depth modifiers**: each band of vertical separation between firer and target reduces damage by 1 (min 1).

### Worked example

Player A attacks with **Type-VII U-boat** (3 power / 2 hull, at DEEP, undetected) targeting Player B's Flagship (at PERISCOPE).
Player A also attacks with **Surface Raider** (4 power / 4 hull, at SURFACE, detected from a previous turn) targeting B's Flagship.

**Detection step**: Player B has 3 Sonar Charges. Detecting Type-VII at DEEP costs `1 + 2 = 3`. B spends all three Sonar; Type-VII is now detected.

**Interceptor step**: Player B has one Vessel, **Coastal Sub** (2 power / 3 hull, at PERISCOPE). It can intercept Surface Raider (1 band away — legal) or Type-VII (3 bands away — illegal, max range 1). B declares Coastal Sub blocks Surface Raider.

**Damage step**:
- Surface Raider (4 power) and Coastal Sub (2 power) deal damage to each other. Surface Raider takes 2, surviving with 2/4. Coastal Sub takes 4, exceeds its hull of 3, sinks.
- Type-VII (3 power) hits Flagship. Depth separation: DEEP to PERISCOPE = 2 bands. Damage reduced by 2 → 1 damage to Flagship.

**End of combat**: Flagship at 24/25, Surface Raider tapped at 2/4, Type-VII tapped at 2/2 undamaged, Coastal Sub in Wreckage. Both attackers' `detected` flag persists into next turn (decays at end of *next* Surface phase via the Sonar Decay step).

This is implementable as a subclass of `CombatManager` (call it `DepthsCombatManager`) that inserts a Detection Resolution sub-step before block declaration, looks up `obj.state.depth_band` for the modifier math, and reads `obj.state.detected` to gate target legality. No new pipeline phase, no new event ordering — every step emits a normal `Event` that interceptors can hook.

> **Why it's submarine-y**: Real ASW (anti-submarine warfare) is a detection problem first and a damage problem second. A Type-VII that you never detected hit your battleship for full damage; a Type-VII you pinged at DEEP got hunted down. The two-step Detect-then-Intercept loop captures that exactly.

---

## 6. Card Types

Six card types. The first four require new `CardType` enum entries (prefix `DEPTHS_`); the last two reuse existing entries.

| Type | Enum | Role |
|------|------|------|
| **Vessel** | `DEPTHS_VESSEL` | The creature analogue. Has power, hull, depth_band. Subtypes: Submarine, Destroyer, Carrier, Drone, Flagship |
| **Crew** | `DEPTHS_CREW` | Equipment-style attachment. Boosts host Vessel's power/hull or grants keywords (Stealth, Reach, Silent Running) |
| **Weapon** | `DEPTHS_WEAPON` | Attached ordnance. Adds activated abilities to host Vessel (e.g. "{1T}: deal 2 to a target Vessel"). Limited charges |
| **Mine** | `DEPTHS_MINE` | Battlefield permanent at a chosen depth band. Triggers when an opposing Vessel enters or attacks from that band. One-shot — sinks after firing |
| **Action** | `INSTANT` (reused) | One-shot effect. Played at sorcery speed during your Maneuver/Regroup phase. "Volley", "Decoy", "Crash Dive" |
| **Doctrine** | `ENCHANTMENT` (reused) | Persistent global effect. "Wolfpack Tactics — your Submarine Vessels get +1/+0", "Iron Discipline — your Vessels can't be detected at DEEP" |

Reusing `INSTANT` and `ENCHANTMENT` for Action and Doctrine lets us inherit the existing cast-from-hand → stack → resolve pipeline without writing new spell-resolution code; we just relabel them in the frontend.

---

## 7. Engine Capabilities

The engine must natively support:

- **ETB triggers** ("when this Vessel enters the battlefield...") — already exists, use `make_etb_trigger`
- **Death/sink triggers** ("when this Vessel is sunk...") — already exists, use `make_death_trigger`
- **Attack triggers** ("whenever this attacks...") — already exists
- **Static effects on the battlefield** ("your Submarines have +1 power") — `make_static_pt_boost` works
- **Activated abilities with charge costs** ("{1T}: deal 2 damage to target Vessel") — use `make_activated_ability`, but cost parsing must accept `T`/`S` symbols
- **Attach mechanic** (Crew → Vessel, Weapon → Vessel) — reuse `make_equipment_setup` pattern
- **Counters** — depth band stored as enum in `obj.state.depth_band`; oxygen as integer counter; charge counters on Weapons
- **Replacement effects** — depth modifiers on damage (the "−1 per band of separation" math) is a TRANSFORM-priority interceptor on `DAMAGE` events
- **State-based check** — Vessel sinks when `damage >= hull`; Flagship loss; scuttle-loss check
- **New events to add to `EventType`**: `DEPTHS_DIVE`, `DEPTHS_SURFACE_VESSEL`, `DEPTHS_DETECT`, `DEPTHS_DETECTION_FAIL`, `DEPTHS_PING_DECAY`, `DEPTHS_LAY_MINE`, `DEPTHS_MINE_TRIGGER`, `DEPTHS_RESUPPLY`, `DEPTHS_OXYGEN_TICK`
- **New keywords**: `stealth` (enters undetected), `silent_running` (cost +1 Sonar to detect), `reach` (can intercept across 2 depth bands), `bottom_crawler` (immune to depth charges), `homing` (ignores depth modifier on damage)
- **Targeting filter extensions**: "target Vessel at depth X", "target undetected Vessel", "target detected Vessel" — these are new `TargetFilter` factories, not new engine primitives

What the engine **does NOT** need to support (and the design avoids):
- No partial-information mechanics (everything including depth is public)
- No simultaneous secret bidding
- No real-time elements
- No replacement-effect chains beyond depth-damage modifier
- No multiplayer-specific zones

This list bounds the first 150 cards — every card in the starter set is implementable as some combination of the above primitives.

---

## 8. AI Difficulty Model

Three tiers via `DepthsAIAdapter(difficulty: str)`. All three share the same legal-move generator; they differ in **selection policy**.

### Easy
Random legal moves with two safety floors:
- Always plays a Vessel if it can afford one and the board has fewer than 3 friendly Vessels
- Will not deliberately attack into a known-lethal interceptor (one-step lookahead on its own attacker's survival only)

This produces a fleet that builds toward the engagement but plays it badly — perfect for a tutorial opponent.

### Medium
Greedy heuristic, no lookahead. For each phase the AI scores all legal actions with hand-tuned weights:
- **Deployment**: prefers Vessels whose `(power + hull) / cost` exceeds 1.5
- **Diving**: dives undetected Vessels toward DEEP if they have power ≥ 3; surfaces Vessels if any opposing Mine is at their depth
- **Detection**: spends Sonar to detect attackers whose unintercepted damage would exceed the Flagship's remaining hull buffer (life - 5)
- **Attacking**: attacks if expected damage to Flagship ≥ 2, breaks ties by preferring to sink high-value enemy Vessels
- **No turn lookahead**

### Hard
Lookahead-1 with value heuristics. For its own turn, the Hard AI:
1. Generates the top-K (K=5) candidate action sequences by greedy expansion from each phase
2. For each candidate, simulates one full turn forward and scores the resulting board state with a weighted value function: `0.6*flagship_hull_diff + 0.3*board_value_diff + 0.1*charge_economy_diff`
3. Picks the sequence with the highest projected score

Hard AI also **predicts the opponent's detection budget**: it tracks opponent's Sonar Charges and prefers to attack with stealth-keyword Vessels when the opponent cannot afford to detect them all. This is the equivalent of a real-world wolfpack commander coordinating a saturation strike.

No tier uses MCTS or neural eval — keeps the AI fast and the heuristics readable / debuggable, matching the Hearthstone and Pokemon adapters in this repo.

---

## 9. Comparison with Existing Engines

**Closest cousin: Minecraft.** Both engines layer a small spatial structure (Minecraft's 3x3 grid + 3 biomes; Depths' 5-band depth ladder) on top of the standard battlefield, both abandon the MTG priority loop in favor of a phase-driven turn manager, and both use multi-resource economies (Minecraft's 5 materials; Depths' 2 charge pools). Depths borrows Minecraft's pattern of putting spatial state in `obj.state.<field>` rather than introducing a new `ZoneType` for each tile.

**Where Depths diverges from Minecraft**: Minecraft's grid is a *building* metaphor (place structures in cells); Depths' depth ladder is a *positioning* metaphor (Vessels move freely between bands). Minecraft's combat is column-gated (frontmost-blocks); Depths' combat is detection-gated (visible-can-be-blocked). Minecraft has no stealth analogue; Depths makes stealth-vs-detection the central tension.

**Versus MTG**: Depths drops the priority loop, drops the cleanup-step damage heal (sub damage persists, must be repaired), drops mana for charge stockpiles, and adds the Depth Ladder as a hard targeting gate. Combat is simultaneous (no first/second strike) and uses a depth-modifier damage formula that MTG does not.

**Versus Hearthstone**: Depths borrows the ramping per-turn resource cap and the "no priority responses" simplification, but rejects HS's max-7-board (we want fleets to feel large) and HS's hand-burn (we want resource decisions to be about *charges*, not cards). Detection resolution is something HS has no equivalent of — the closest analogue would be Stealth, which is a less interesting one-shot keyword.

**Versus Pokemon**: Pokemon's energy-attachment model is the wrong shape for submarines (subs don't get more powerful by attaching torpedoes; they fire torpedoes and run out). Both share the "Flagship = life total" framing (Pokemon's Active Pokemon ↔ Depths' Flagship), but Depths' Flagship can take damage without rotating out — there is no "bench" because the depth ladder *is* the bench-equivalent.

**Versus Yu-Gi-Oh**: YGO has zero overlap. No phase resemblance, no spell speed analogue, no monster summoning ladder. Mention only to dismiss.

**Net design statement**: Depths is "Minecraft's spatial combat + Hearthstone's economy + a stealth/detection sub-game that neither has." If you understand Minecraft's `column_target` function, you'll understand Depths' depth-band targeting in 30 seconds.

---

## Pipeline Summary (auto-generated 2026-05-06)

`/new-game "submarine fleet"` end-to-end run. Stages 0–9, fire-and-forget.

### Engine modules
- `src/engine/depths.py` (1335 LOC) — game-state, charges, mode adapter, system interceptors, action handlers
- `src/engine/depths_combat.py` (1057 LOC) — combat manager + Detection Resolution sub-step + depth-modifier interceptor
- `src/engine/depths_turn.py` (1283 LOC) — 5-phase turn manager (DIVE → MANEUVER → ENGAGEMENT → REGROUP → SURFACE)
- `src/ai/depths_adapter.py` (1370 LOC) — three-tier AI (random / greedy / lookahead-1)
- `src/engine/types.py` extended with 4 new CardType enums (`DEPTHS_VESSEL`/`CREW`/`WEAPON`/`MINE`) + 9 new EventType enums + ObjectState fields (`depth_band`, `detected`, `oxygen`) + Player fields (`tc`, `sc`, `flagship_id`)

### Frontend
- `frontend/src/games/depths.tsx` (1019 LOC) — 5-band depth-ladder board, dark/sonar palette
- `frontend/src/hooks/useDepthsGame.ts` — depths-aware data hook
- `npm run build` clean; engine registered in `frontend/src/games/registry.ts`

### First set (SUBS)
- `docs/sets/SUBS.md` — 150-card design with 5 mechanics (SILENT RUNNING / WOLFPACK N / CHARGE-SWAP / CRUSH-DIVE / SHADOW-COUNT)
- `src/cards/depths/submarine_fleet/` — 5 archetype files + factories + style + decks aggregating to `SUBS_CARDS`
- 4 starter decks: `SUBS_wolfpack`, `SUBS_silent_hunter`, `SUBS_carrier`, `SUBS_deep_strike` (30 cards each)
- 150 placeholder PNGs in `assets/card_art/depths/submarine_fleet/` (stage 5 fell back to `--mode local` per fire-and-forget rule; ChatGPT browser automation skipped because no logged-in session was guaranteed)
- `tests/test_depths_smoke.py` (engine) and `tests/test_subs.py` (set) — both green

### Balance loop — cycle 1 (NOT converged)

Tournament: 30 games (4 decks × 6 pairings × 5 games), 0 errors, ~0.7s wall time.

**Archetype winrates** (target 40–60%):
| Archetype | Winrate | Verdict |
|---|---|---|
| SUBS_wolfpack | **93.3%** | OVERPOWERED |
| SUBS_silent_hunter | 53.3% | OK |
| SUBS_deep_strike | 40.0% | OK |
| SUBS_carrier | **0.0%** | UNDERPOWERED |

**Per-card flags**: 5 underpowered (all Carrier — Pilot Cadet / Recon Drone / Escort Carrier / Fleet Carrier "Hiryu" / Light Carrier "Shoho"). 0 overpowered: Wolfpack's dominance is uniform across the deck, not driven by one card.

**Coverage**: 6 zero-play cards. 5 are Doctrines (`Wolfpack Doctrine`, `Iron Discipline`, `Carrier Air Wing Doctrine`, `Crush-Depth Doctrine`, `Battery Reroute`) — the AI never plays them because Doctrine deployment isn't in its action menu. The 6th is the placeholder `Battleship Flagship` (installed via `setup_depths_player`, not cast).

**Convergence**: cycles 2–10 of revision were skipped — meaningful re-balancing requires fixing the underlying engine gaps first (see TODOs below). Running revision agents on top of an AI that can't deploy Doctrines would just churn cards without affecting the actual problem.

### Outstanding engine TODOs (block balance work)

Card-implementation agents flagged ~25 `# TODO:` markers, clustered around features the engine doesn't yet expose:

1. **AI doesn't deploy Doctrines** → Carrier and Wolfpack archetype anthems never resolve. Highest-impact fix.
2. **No QUERY_COST event** → cost-modifier cards (Bathyscaphe Pilot / Dive Master / Deep Vector Doctrine / Compass Officer) are stubs.
3. **No QUERY_DETECTION_COST event** → Sonar Jammer / Thermocline Cloak stubs; Iron Discipline only blocks the detect event after spend, not the spend itself.
4. **No EOT keyword grant primitive** → "homing EOT" and similar use a `_temp_keywords_eot` state-stash convention that combat code doesn't yet read.
5. **No damage-prevention shield helper** → Brace for Impact stubbed.
6. **No interactive Action targeting** → Action effects auto-pick "best legal target" rather than prompting; mostly fine for AI play, but limits human-vs-AI fidelity.

### How to play (engine + UI)
- Backend: `Game(mode="depths")` + `setup_depths_player(game, player, deck, flagship_def)` per docs.
- AI: `DepthsAIAdapter(difficulty="medium")` registered via `tm.set_ai_handler(handler, player_id=p.id)`.
- Frontend route + server wiring: not yet plumbed (Stage 7 of /new-game omitted server-side game-mode dispatch). The board component is built; the `/game/:matchId/depths` route + `mode="depths"` server handler remain.

### What this run produced for you
**14,113 LOC** of engine + cards + frontend + tests + adapter, plus 150 placeholder card PNGs and a baseline tournament JSON showing the next-step priorities. Estimated cost vs the original 4–12hr promise: ran in ~2 hours of conversation time, primarily because the parallel-agent integration produced more friction than the rosy estimate accounted for.

